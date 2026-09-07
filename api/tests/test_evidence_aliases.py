from urllib.parse import quote

from action.models import DeviceLog
from evidence.models import RootAlias
from lot.models import DeviceLot
from user.models import Institution

from api.tests.base import ApiTestCase


URL = "/api/v1/evidence/"


class SetEvidenceAliasTest(ApiTestCase):
    """PUT /evidence/{alias}/aliases/{root}/ rewrites the canonical id an
    evidence answers to, the same way the web alias form does."""

    def setUp(self):
        super().setUp()
        self.root = self.device_root("abc123")
        self.cache, self.prop = self.make_device(self.root)

    def put(self, alias, root, auth=True):
        credentials = self.auth if auth else {}
        return self.client.put(
            "{}{}/aliases/{}/".format(URL, alias, root), **credentials)

    def stored_root(self, alias=None, institution=None):
        return RootAlias.objects.get(
            owner=institution or self.institution, alias=alias or self.root).root

    def test_unknown_root_becomes_a_custom_id(self):
        response = self.put(self.root, "inv-9")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["root"], "custom_id:inv-9")
        self.assertEqual(self.stored_root(), "custom_id:inv-9")

    def test_existing_evidence_is_taken_as_the_root_itself(self):
        other = self.device_root("def456")
        self.make_device(other)
        response = self.put(self.root, other)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_root(), other)

    def test_wanted_root_is_lowercased(self):
        self.put(self.root, "INV-9")
        self.assertEqual(self.stored_root(), "custom_id:inv-9")

    def test_surrounding_blanks_are_ignored(self):
        response = self.put(quote(" {} ".format(self.root)), quote(" inv-9 "))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alias"], self.root)
        self.assertEqual(self.stored_root(), "custom_id:inv-9")

    def test_blank_root_is_rejected(self):
        response = self.put(self.root, quote("  "))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.stored_root(), self.root)

    def test_repeating_the_call_keeps_the_same_root(self):
        self.put(self.root, "inv-9")
        response = self.put(self.root, "inv-9")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_root(), "custom_id:inv-9")
        self.assertEqual(DeviceLog.objects.count(), 1)

    def test_change_is_logged_against_the_evidence(self):
        self.put(self.root, "inv-9")
        log = DeviceLog.objects.get(institution=self.institution)
        self.assertEqual(log.snapshot_uuid, self.prop.uuid)
        self.assertIn("custom_id:inv-9", log.event)
        self.assertIn(self.root, log.event)

    def test_lot_membership_follows_the_new_root(self):
        lot = self.make_lot()
        DeviceLot.objects.create(lot=lot, device_id=self.root)
        self.put(self.root, "inv-9")
        self.assertEqual(
            list(lot.devicelot_set.values_list("device_id", flat=True)),
            ["custom_id:inv-9"])

    def test_unknown_evidence_is_rejected(self):
        response = self.put(self.device_root("nothinghere"), "inv-9")
        self.assertEqual(response.status_code, 404)

    def test_evidence_of_another_institution_is_rejected(self):
        other = Institution.objects.create(name="OtherOrg")
        root = self.device_root("otherorg")
        self.make_device(root, institution=other,
                         user=self.make_user(other, "other@test.com"))
        self.assertEqual(self.put(root, "inv-9").status_code, 404)
        self.assertEqual(self.stored_root(root, institution=other), root)

    def test_pointing_an_evidence_to_itself_is_rejected(self):
        response = self.put(self.root, self.root)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.stored_root(), self.root)

    def test_aliased_target_is_rejected(self):
        other = self.device_root("def456")
        self.make_device(other)
        RootAlias.set_alias(
            owner=self.institution, alias=other, new_root="custom_id:inv-9")
        response = self.put(self.root, other)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stored_root(), self.root)

    def test_evidence_with_dependents_cannot_be_rerooted(self):
        other = self.device_root("def456")
        self.make_device(other)
        RootAlias.set_alias(
            owner=self.institution, alias=other, new_root=self.root)
        response = self.put(self.root, "inv-9")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stored_root(), self.root)

    def test_anonymous_request_is_rejected(self):
        self.assertEqual(self.put(self.root, "inv-9", auth=False).status_code, 401)
        self.assertEqual(self.stored_root(), self.root)


class ResetEvidenceAliasTest(ApiTestCase):
    """DELETE /evidence/{alias}/aliases/ gives an evidence its own id back."""

    def setUp(self):
        super().setUp()
        self.root = self.device_root("abc123")
        self.cache, self.prop = self.make_device(self.root)

    def delete(self, alias, auth=True):
        credentials = self.auth if auth else {}
        return self.client.delete(
            "{}{}/aliases/".format(URL, alias), **credentials)

    def stored_root(self, alias=None, institution=None):
        return RootAlias.objects.get(
            owner=institution or self.institution, alias=alias or self.root).root

    def test_aliased_evidence_becomes_canonical_again(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        response = self.delete(self.root)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["root"], self.root)
        self.assertEqual(self.stored_root(), self.root)

    def test_row_is_kept_as_a_self_reference(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        self.delete(self.root)
        self.assertTrue(RootAlias.objects.filter(
            owner=self.institution, alias=self.root).exists())

    def test_lot_membership_comes_back_to_the_evidence(self):
        lot = self.make_lot()
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        DeviceLot.objects.create(lot=lot, device_id="custom_id:inv-9")
        self.delete(self.root)
        self.assertEqual(
            list(lot.devicelot_set.values_list("device_id", flat=True)),
            [self.root])

    def test_reset_is_logged_against_the_evidence(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        self.delete(self.root)
        log = DeviceLog.objects.get(institution=self.institution)
        self.assertEqual(log.snapshot_uuid, self.prop.uuid)
        self.assertIn("custom_id:inv-9", log.event)

    def test_canonical_evidence_is_left_untouched(self):
        response = self.delete(self.root)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_root(), self.root)
        self.assertFalse(DeviceLog.objects.exists())

    def test_surrounding_blanks_are_ignored(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        response = self.delete(quote(" {} ".format(self.root)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_root(), self.root)

    def test_unknown_evidence_is_rejected(self):
        self.assertEqual(self.delete(self.device_root("nothinghere")).status_code, 404)

    def test_evidence_of_another_institution_is_rejected(self):
        other = Institution.objects.create(name="OtherOrg")
        root = self.device_root("otherorg")
        self.make_device(root, institution=other,
                         user=self.make_user(other, "other@test.com"))
        RootAlias.set_alias(owner=other, alias=root, new_root="custom_id:inv-9")
        self.assertEqual(self.delete(root).status_code, 404)
        self.assertEqual(self.stored_root(root, institution=other), "custom_id:inv-9")

    def test_anonymous_request_is_rejected(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root, new_root="custom_id:inv-9")
        self.assertEqual(self.delete(self.root, auth=False).status_code, 401)
        self.assertEqual(self.stored_root(), "custom_id:inv-9")

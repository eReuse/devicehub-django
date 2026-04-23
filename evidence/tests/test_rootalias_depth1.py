import uuid

from django.test import TestCase

from user.models import Institution, User
from evidence.models import SystemProperty, RootAlias
from lot.models import (
    Lot,
    LotTag,
    DeviceLot,
    Beneficiary,
    DeviceBeneficiary,
    LotSubscription,
)


class RootAliasDepth1Tests(TestCase):
    """RootAlias must behave as a depth-1 graph: every ``alias -> root``
    lands on a terminal node (``root.alias == root.root`` or no row for
    ``root``), and no alias can be re-rooted while others depend on it.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value=value,
        )

    # -- is_terminal_root ------------------------------------------------

    def test_is_terminal_root_true_for_missing_target(self):
        # fresh custom_id not backed by a SystemProperty
        self.assertTrue(
            RootAlias.is_terminal_root(self.institution, "custom_id:X")
        )

    def test_is_terminal_root_true_for_self_reference(self):
        self._sp("ereuse28:a3")
        self.assertTrue(
            RootAlias.is_terminal_root(self.institution, "ereuse28:a3")
        )

    def test_is_terminal_root_false_when_target_is_aliased(self):
        self._sp("ereuse26:a2")
        self._sp("ereuse28:a3")
        RootAlias.set_alias(
            self.institution, "ereuse26:a2", "ereuse28:a3",
        )
        self.assertFalse(
            RootAlias.is_terminal_root(self.institution, "ereuse26:a2")
        )

    # -- has_dependents --------------------------------------------------

    def test_has_dependents_false_for_lone_self_ref(self):
        self._sp("a1")
        self.assertFalse(RootAlias.has_dependents(self.institution, "a1"))

    def test_has_dependents_true_when_other_alias_points_to_it(self):
        self._sp("a1")
        self._sp("a2")
        RootAlias.set_alias(self.institution, "a1", "a2")
        self.assertTrue(RootAlias.has_dependents(self.institution, "a2"))

    # -- set_alias happy paths ------------------------------------------

    def test_set_alias_creates_depth1_edge(self):
        self._sp("ereuse24:a1")
        self._sp("ereuse28:a3")
        RootAlias.set_alias(
            self.institution, "ereuse24:a1", "ereuse28:a3"
        )
        ra = RootAlias.objects.get(
            owner=self.institution, alias="ereuse24:a1"
        )
        self.assertEqual(ra.root, "ereuse28:a3")

    def test_set_alias_idempotent(self):
        self._sp("a1")
        self._sp("a2")
        RootAlias.set_alias(self.institution, "a1", "a2")
        # re-applying the same edge must succeed (no dependents created yet)
        RootAlias.set_alias(self.institution, "a1", "a2")
        self.assertEqual(
            RootAlias.objects.filter(
                owner=self.institution, alias="a1"
            ).count(),
            1,
        )

    def test_set_alias_allows_pointing_to_missing_custom_id(self):
        self._sp("ereuse24:a1")
        RootAlias.set_alias(
            self.institution, "ereuse24:a1", "custom_id:X",
        )
        ra = RootAlias.objects.get(
            owner=self.institution, alias="ereuse24:a1"
        )
        self.assertEqual(ra.root, "custom_id:X")

    # -- set_alias rejects chains ---------------------------------------

    def test_set_alias_rejects_non_terminal_target(self):
        # a1 -> a2 -> a3 attempted
        self._sp("a1")
        self._sp("a2")
        self._sp("a3")
        RootAlias.set_alias(self.institution, "a2", "a3")
        with self.assertRaises(ValueError):
            RootAlias.set_alias(self.institution, "a1", "a2")

    def test_set_alias_rejects_reroot_when_dependents_exist(self):
        # a1 -> a2 (self-ref) ; trying to change a2 -> a3 would orphan a1
        self._sp("a1")
        self._sp("a2")
        self._sp("a3")
        RootAlias.set_alias(self.institution, "a1", "a2")
        with self.assertRaises(ValueError):
            RootAlias.set_alias(self.institution, "a2", "a3")

    def test_set_alias_allows_self_ref_even_with_dependents(self):
        # a1 -> a2 ; setting a2 -> a2 (self) should not break anyone
        self._sp("a1")
        self._sp("a2")
        RootAlias.set_alias(self.institution, "a1", "a2")
        # a2 already self-refs via the signal; explicit set must be ok
        RootAlias.set_alias(self.institution, "a2", "a2")
        ra = RootAlias.objects.get(owner=self.institution, alias="a2")
        self.assertEqual(ra.root, "a2")


class RootAliasSyncMembershipsTests(TestCase):
    """set_alias must collapse DeviceLot/DeviceBeneficiary rows that
    belong to the same canonical device, the same way migration 0012 did.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="m@test.local", institution=self.institution
        )
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="m", owner=self.institution, type=self.tag
        )
        for v in ["x1", "x2"]:
            SystemProperty.objects.create(
                owner=self.institution, uuid=uuid.uuid4(), value=v,
            )

    def test_set_alias_collapses_existing_devicelot_rows(self):
        """Scenario: two devices in a lot, then both aliased to the same
        custom_id. The lot must end up with one row, not two.
        """
        self.lot.add("x1")
        self.lot.add("x2")
        self.assertEqual(
            DeviceLot.objects.filter(lot=self.lot).count(), 2
        )

        RootAlias.set_alias(self.institution, "x1", "custom_id:A1")
        RootAlias.set_alias(self.institution, "x2", "custom_id:A1")

        rows = DeviceLot.objects.filter(lot=self.lot)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().device_id, "custom_id:A1")

    def test_set_alias_rewrites_devicelot_to_new_root(self):
        self.lot.add("x1")
        RootAlias.set_alias(self.institution, "x1", "custom_id:A1")
        self.assertEqual(
            DeviceLot.objects.get(lot=self.lot).device_id,
            "custom_id:A1",
        )

    def test_set_alias_reset_to_self_ref_is_allowed(self):
        """Resetting alias -> alias must succeed even when the current
        root is not terminal (pre-existing custom edge)."""
        RootAlias.set_alias(self.institution, "x1", "custom_id:A")
        # "Delete" the alias — resets to self-reference.
        RootAlias.set_alias(self.institution, "x1", "x1")
        ra = RootAlias.objects.get(owner=self.institution, alias="x1")
        self.assertEqual(ra.root, "x1")

    def test_reset_migrates_orphan_lot_row_back_to_alias(self):
        """If the device was the only member of its alias group, the lot
        row under old_root would be orphaned after reset; migrate it."""
        self.lot.add("x1")
        RootAlias.set_alias(self.institution, "x1", "custom_id:solo")
        self.assertEqual(
            DeviceLot.objects.get(lot=self.lot).device_id,
            "custom_id:solo",
        )
        RootAlias.set_alias(self.institution, "x1", "x1")
        self.assertEqual(
            DeviceLot.objects.get(lot=self.lot).device_id, "x1"
        )

    def test_reset_does_not_disturb_shared_group_row(self):
        """If other aliases still share old_root, the (lot, old_root)
        row represents the remaining group members; do not touch it."""
        self.lot.add("x1")
        self.lot.add("x2")
        RootAlias.set_alias(self.institution, "x1", "custom_id:A")
        RootAlias.set_alias(self.institution, "x2", "custom_id:A")
        # one collapsed row now
        self.assertEqual(
            DeviceLot.objects.filter(lot=self.lot).count(), 1
        )
        # x1 leaves the group; x2 remains under custom_id:A
        RootAlias.set_alias(self.institution, "x1", "x1")
        row = DeviceLot.objects.get(lot=self.lot)
        self.assertEqual(row.device_id, "custom_id:A")

    def test_set_alias_collapses_existing_devicebeneficiary_rows(self):
        shop = LotSubscription.objects.create(
            lot=self.lot, user=self.user, type=LotSubscription.Type.SHOP,
        )
        b = Beneficiary.objects.create(
            lot=self.lot, shop=shop, email="b@test.local",
        )
        # Bypass Beneficiary.add's per-lot dedup to seed two physical rows
        DeviceBeneficiary.objects.create(
            beneficiary=b, device_id="x1",
            status=DeviceBeneficiary.Status.INTERESTED,
        )
        DeviceBeneficiary.objects.create(
            beneficiary=b, device_id="x2",
            status=DeviceBeneficiary.Status.INTERESTED,
        )

        RootAlias.set_alias(self.institution, "x1", "custom_id:A1")
        RootAlias.set_alias(self.institution, "x2", "custom_id:A1")

        rows = DeviceBeneficiary.objects.filter(beneficiary=b)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().device_id, "custom_id:A1")

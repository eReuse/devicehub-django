from django.test import TestCase, Client
from django.urls import reverse

from dhemail.models import InstitutionTemplate, LotTemplate
from lot.models import Lot, LotTag
from user.models import Institution, User
from user.views import EDITABLE_GROUPS, _template_name


VALID_GROUP = EDITABLE_GROUPS[0][0]   # 'ben_interested'
VALID_PATH = EDITABLE_GROUPS[0][2][2][1]  # email.html for ben_interested
VALID_TMPL_NAME = _template_name(VALID_PATH)


class LotTemplateEditorAccessTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()

        self.plain = User.objects.create_user(
            email="plain@test.com", institution=self.institution, password="pass"
        )
        self.url = reverse("lot:template-editor", kwargs={
            "pk": self.lot.id, "group_id": VALID_GROUP
        })

    def test_anonymous_redirects(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_plain_user_gets_403(self):
        c = Client()
        c.login(username="plain@test.com", password="pass")
        response = c.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access(self):
        c = Client()
        c.login(username="admin@test.com", password="pass")
        response = c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_lot_from_other_institution_returns_404(self):
        other = Institution.objects.create(name="Other")
        other_tag = LotTag.objects.create(name="OtherTag", owner=other)
        other_lot = Lot.objects.create(name="OtherLot", owner=other, type=other_tag)
        url = reverse("lot:template-editor", kwargs={
            "pk": other_lot.id, "group_id": VALID_GROUP
        })
        c = Client()
        c.login(username="admin@test.com", password="pass")
        response = c.get(url)
        self.assertEqual(response.status_code, 404)


class LotTemplateEditorGetTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass")
        self.url = reverse("lot:template-editor", kwargs={
            "pk": self.lot.id, "group_id": VALID_GROUP
        })

    def test_shows_lot_content_when_saved(self):
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=VALID_TMPL_NAME,
            content="custom lot text\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "custom lot text")

    def test_shows_institution_content_as_fallback(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=VALID_TMPL_NAME,
            content="institution fallback\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "institution fallback")

    def test_lot_content_takes_priority_over_institution(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=VALID_TMPL_NAME,
            content="institution content\n",
        )
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=VALID_TMPL_NAME,
            content="lot content\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "lot content")
        self.assertNotContains(response, "institution content")

    def test_shows_lot_badge_when_lot_template_exists(self):
        LotTemplate.objects.create(
            lot=self.lot, template_name=VALID_TMPL_NAME, content="x\n"
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'badge bg-success')  # 'lot' badge

    def test_shows_institution_badge_when_only_institution_template_exists(self):
        InstitutionTemplate.objects.create(
            institution=self.institution, template_name=VALID_TMPL_NAME, content="x\n"
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'badge bg-warning')  # 'institution' badge

    def test_shows_default_badge_when_no_db_entry(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'badge bg-secondary')  # 'default' badge


class LotTemplateEditorPostTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass")
        self.url = reverse("lot:template-editor", kwargs={
            "pk": self.lot.id, "group_id": VALID_GROUP
        })

    def test_post_saves_lot_template(self):
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "my lot content",
        })
        tmpl = LotTemplate.objects.get(lot=self.lot, template_name=VALID_TMPL_NAME)
        self.assertIn("my lot content", tmpl.content)

    def test_post_does_not_affect_institution_template(self):
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "lot only",
        })
        self.assertEqual(
            InstitutionTemplate.objects.filter(institution=self.institution).count(), 0
        )

    def test_post_updates_existing_lot_template(self):
        LotTemplate.objects.create(
            lot=self.lot, template_name=VALID_TMPL_NAME, content="old\n"
        )
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "new content",
        })
        tmpl = LotTemplate.objects.get(lot=self.lot, template_name=VALID_TMPL_NAME)
        self.assertIn("new content", tmpl.content)

    def test_post_rejects_invalid_rel_path(self):
        self.client.post(self.url, {
            "rel_path": "../../etc/passwd",
            "content": "malicious",
        })
        self.assertEqual(LotTemplate.objects.filter(lot=self.lot).count(), 0)

    def test_post_does_not_affect_other_lot(self):
        lot2 = Lot.objects.create(name="Lot 2", owner=self.institution, type=self.tag)
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "content",
        })
        self.assertEqual(LotTemplate.objects.filter(lot=lot2).count(), 0)

    def test_post_redirects_to_same_group(self):
        response = self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "x",
        })
        self.assertRedirects(response, self.url)

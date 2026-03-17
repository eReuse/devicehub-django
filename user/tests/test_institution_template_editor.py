from django.test import TestCase, Client
from django.urls import reverse

from dhemail.models import InstitutionTemplate
from lot.models import Lot, LotTag
from user.models import Institution, User
from user.views import EDITABLE_GROUPS, _template_name


VALID_GROUP = EDITABLE_GROUPS[0][0]   # 'ben_interested'
VALID_PATH = EDITABLE_GROUPS[0][2][2][1]  # 'dhemail/templates/beneficiary/interested/email.html'
VALID_TMPL_NAME = _template_name(VALID_PATH)


class InstitutionTemplateEditorAccessTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()

        self.shop = User.objects.create_user(
            email="shop@test.com", institution=self.institution, password="pass"
        )
        self.shop.is_shop = True
        self.shop.save()

        self.plain = User.objects.create_user(
            email="plain@test.com", institution=self.institution, password="pass"
        )
        self.url = reverse("user:template-editor", kwargs={"group_id": VALID_GROUP})

    def test_anonymous_redirects_to_login(self):
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

    def test_shop_can_access(self):
        c = Client()
        c.login(username="shop@test.com", password="pass")
        response = c.get(self.url)
        self.assertEqual(response.status_code, 200)


class InstitutionTemplateEditorGetTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass")
        self.url = reverse("user:template-editor", kwargs={"group_id": VALID_GROUP})

    def test_shows_all_groups_in_nav(self):
        response = self.client.get(self.url)
        for gid, glabel, _ in EDITABLE_GROUPS:
            self.assertContains(response, glabel)

    def test_active_group_is_highlighted(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'nav-link active')

    def test_shows_institution_content_when_saved(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=VALID_TMPL_NAME,
            content="custom institution text\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "custom institution text")

    def test_shows_file_paths_for_active_group(self):
        response = self.client.get(self.url)
        # The active group's file paths should appear in the page
        self.assertContains(response, "beneficiary/interested")


class InstitutionTemplateEditorPostTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.admin = User.objects.create_user(
            email="admin@test.com", institution=self.institution, password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass")
        self.url = reverse("user:template-editor", kwargs={"group_id": VALID_GROUP})

    def test_post_saves_institution_template(self):
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "my new content",
        })
        tmpl = InstitutionTemplate.objects.get(
            institution=self.institution, template_name=VALID_TMPL_NAME
        )
        self.assertIn("my new content", tmpl.content)

    def test_post_updates_existing_template(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=VALID_TMPL_NAME,
            content="old content\n",
        )
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "updated content",
        })
        tmpl = InstitutionTemplate.objects.get(
            institution=self.institution, template_name=VALID_TMPL_NAME
        )
        self.assertIn("updated content", tmpl.content)

    def test_post_redirects_to_same_group(self):
        response = self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "x",
        })
        self.assertRedirects(response, self.url)

    def test_post_rejects_invalid_rel_path(self):
        self.client.post(self.url, {
            "rel_path": "../../etc/passwd",
            "content": "malicious",
        })
        self.assertEqual(
            InstitutionTemplate.objects.filter(institution=self.institution).count(), 0
        )

    def test_post_does_not_affect_other_institution(self):
        other = Institution.objects.create(name="Other Institution")
        self.client.post(self.url, {
            "rel_path": VALID_PATH,
            "content": "content",
        })
        self.assertEqual(
            InstitutionTemplate.objects.filter(institution=other).count(), 0
        )

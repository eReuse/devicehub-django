from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from dashboard.help import help_url
from user.models import Institution, User

BASE = "https://docs.ereuse.org/help/"


class HelpUrlTests(SimpleTestCase):
    def test_english_is_the_root_of_the_help_site(self):
        self.assertEqual(
            help_url("admin/#states", language="en"), BASE + "admin/#states")

    def test_spanish_and_catalan_have_their_own_prefix(self):
        self.assertEqual(
            help_url("admin/#states", language="es"),
            BASE + "es/admin/#states")
        self.assertEqual(
            help_url("admin/#states", language="ca"),
            BASE + "ca/admin/#states")

    def test_regional_variants_use_the_base_language(self):
        self.assertEqual(
            help_url("lot/", language="es-ES"), BASE + "es/lot/")
        self.assertEqual(
            help_url("lot/", language="en-us"), BASE + "lot/")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(help_url("lot/", language="fr"), BASE + "lot/")

    def test_empty_page_is_the_help_home_with_trailing_slash(self):
        self.assertEqual(help_url("", language="en"), BASE)
        self.assertEqual(help_url("", language="ca"), BASE + "ca/")

    def test_leading_slash_in_page_is_ignored(self):
        self.assertEqual(help_url("/lot/", language="en"), BASE + "lot/")

    def test_uses_the_active_language_by_default(self):
        with translation.override("ca"):
            self.assertEqual(help_url("lot/"), BASE + "ca/lot/")
        with translation.override("en"):
            self.assertEqual(help_url("lot/"), BASE + "lot/")


class ContextualHelpLinkTests(TestCase):
    """The icon next to the title links to the help of the view; the Help
    entry of the user menu follows it and falls back to the help home."""

    ICON = "fas fa-question-circle text-secondary h6 align-top"

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.admin = User.objects.create(
            email="admin@test.local", institution=self.institution,
            is_admin=True)
        self.client.force_login(self.admin)

    def _get(self, name, lang="en"):
        return self.client.get(reverse(name), HTTP_ACCEPT_LANGUAGE=lang)

    def test_states_panel_icon_is_a_link_to_the_states_help(self):
        html = self._get("admin:states_panel").content.decode()
        self.assertIn(f'href="{BASE}admin/#states"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn(self.ICON, html)

    def test_states_panel_keeps_its_help_text_in_the_tooltip(self):
        html = self._get("admin:states_panel").content.decode()
        self.assertIn("State definitions are the custom finite states", html)

    def test_link_follows_the_user_language(self):
        html = self._get("admin:states_panel", lang="es").content.decode()
        self.assertIn(f'href="{BASE}es/admin/#states"', html)
        self.assertIn('aria-label="Ayuda:', html)

        html = self._get("admin:states_panel", lang="ca").content.decode()
        self.assertIn(f'href="{BASE}ca/admin/#states"', html)

    def test_user_menu_help_points_to_the_view_help(self):
        html = self._get("admin:states_panel").content.decode()
        menu = f'class="dropdown-item" href="{BASE}admin/#states"'
        self.assertIn(menu, html)

    def test_view_without_help_page_has_no_icon_and_menu_goes_to_home(self):
        html = self._get("admin:panel").content.decode()
        self.assertNotIn(self.ICON, html)
        self.assertIn(f'class="dropdown-item" href="{BASE}"', html)

    def test_menu_help_home_follows_the_user_language(self):
        html = self._get("admin:panel", lang="ca").content.decode()
        self.assertIn(f'class="dropdown-item" href="{BASE}ca/"', html)

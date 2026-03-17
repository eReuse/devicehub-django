from django.test import TestCase, Client
from django.urls import reverse

from dhemail.models import InstitutionTemplate, LotTemplate
from lot.models import Donor, Lot, LotTag
from user.models import Institution, User
from user.views import _template_name

TMPL_NAME = _template_name("lot/templates/donor_web_detail.html")


class DonorWebViewTests(TestCase):
    """
    Tests that modifications to donor_web_detail.html at institution or lot
    level are correctly rendered in the donor public page.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        self.donor = Donor.objects.create(lot=self.lot, email="donor@test.com")
        self.url = reverse("lot:web_donor", kwargs={
            "pk": self.lot.id, "id": self.donor.id
        })
        self.client = Client()

    def test_page_is_accessible_without_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_institution_custom_content_appears_in_page(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Custom institution donor text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Custom institution donor text")

    def test_lot_custom_content_appears_in_page(self):
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=TMPL_NAME,
            content="<p>Custom lot donor text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Custom lot donor text")

    def test_lot_content_overrides_institution_content(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Institution donor text</p>\n",
        )
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=TMPL_NAME,
            content="<p>Lot donor text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Lot donor text")
        self.assertNotContains(response, "Institution donor text")

    def test_different_lots_render_their_own_template(self):
        lot2 = Lot.objects.create(name="Lot 2", owner=self.institution, type=self.tag)
        donor2 = Donor.objects.create(lot=lot2, email="donor2@test.com")

        LotTemplate.objects.create(
            lot=self.lot, template_name=TMPL_NAME, content="<p>Lot 1 content</p>\n"
        )
        LotTemplate.objects.create(
            lot=lot2, template_name=TMPL_NAME, content="<p>Lot 2 content</p>\n"
        )

        url2 = reverse("lot:web_donor", kwargs={"pk": lot2.id, "id": donor2.id})
        resp1 = self.client.get(self.url)
        resp2 = self.client.get(url2)

        self.assertContains(resp1, "Lot 1 content")
        self.assertNotContains(resp1, "Lot 2 content")
        self.assertContains(resp2, "Lot 2 content")
        self.assertNotContains(resp2, "Lot 1 content")

    def test_institution_fallback_when_no_lot_template(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Institution fallback</p>\n",
        )
        # No LotTemplate created
        response = self.client.get(self.url)
        self.assertContains(response, "Institution fallback")

from django.test import TestCase, Client
from django.urls import reverse

from dhemail.models import InstitutionTemplate, LotTemplate
from lot.models import Beneficiary, Lot, LotSubscription, LotTag
from user.models import Institution, User
from user.views import _template_name

TMPL_NAME = _template_name("lot/templates/beneficiary_agreement_detail.html")


class BeneficiaryAgreementViewTests(TestCase):
    """
    Tests that modifications to beneficiary_agreement_detail.html at institution
    or lot level are correctly rendered in the beneficiary agreement public page.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        shop_user = User.objects.create_user(
            email="shop@test.com", institution=self.institution, password="pass"
        )
        shop_user.is_shop = True
        shop_user.save()
        self.subscription = LotSubscription.objects.create(
            lot=self.lot, user=shop_user, type=LotSubscription.Type.SHOP
        )
        self.beneficiary = Beneficiary.objects.create(
            lot=self.lot,
            shop=self.subscription,
            email="beneficiary@test.com",
        )
        self.url = reverse("lot:agreement_beneficiary", kwargs={
            "pk": self.lot.id, "id": self.beneficiary.id
        })
        self.client = Client()

    def test_page_is_accessible_without_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_institution_custom_content_appears_in_page(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Custom institution agreement text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Custom institution agreement text")

    def test_lot_custom_content_appears_in_page(self):
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=TMPL_NAME,
            content="<p>Custom lot agreement text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Custom lot agreement text")

    def test_lot_content_overrides_institution_content(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Institution agreement text</p>\n",
        )
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=TMPL_NAME,
            content="<p>Lot agreement text</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Lot agreement text")
        self.assertNotContains(response, "Institution agreement text")

    def test_different_lots_render_their_own_template(self):
        lot2 = Lot.objects.create(name="Lot 2", owner=self.institution, type=self.tag)
        subscription2 = LotSubscription.objects.create(
            lot=lot2,
            user=self.subscription.user,
            type=LotSubscription.Type.SHOP,
        )
        beneficiary2 = Beneficiary.objects.create(
            lot=lot2, shop=subscription2, email="ben2@test.com"
        )
        LotTemplate.objects.create(
            lot=self.lot, template_name=TMPL_NAME, content="<p>Lot 1 agreement</p>\n"
        )
        LotTemplate.objects.create(
            lot=lot2, template_name=TMPL_NAME, content="<p>Lot 2 agreement</p>\n"
        )

        url2 = reverse("lot:agreement_beneficiary", kwargs={
            "pk": lot2.id, "id": beneficiary2.id
        })
        resp1 = self.client.get(self.url)
        resp2 = self.client.get(url2)

        self.assertContains(resp1, "Lot 1 agreement")
        self.assertNotContains(resp1, "Lot 2 agreement")
        self.assertContains(resp2, "Lot 2 agreement")
        self.assertNotContains(resp2, "Lot 1 agreement")

    def test_institution_fallback_when_no_lot_template(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=TMPL_NAME,
            content="<p>Institution fallback</p>\n",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Institution fallback")

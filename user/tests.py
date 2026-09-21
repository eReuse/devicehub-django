import json
import uuid

from django.test import TestCase
from django.urls import reverse

from api.models import Token
from user.models import Institution, User


class TokenQRViewTests(TestCase):
    """The QR carries a credential, so it must only reach its owner."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Test", country="ES")
        self.user = User.objects.create_user("u@example.org", self.institution, "1234")
        self.token = Token.objects.create(
            tag="phone", token=uuid.uuid4(), owner=self.user
        )

    def url(self, token=None):
        return reverse("user:token_qr", args=[(token or self.token).pk])

    def test_owner_gets_a_png(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("no-store", response["Cache-Control"])

    def test_another_user_cannot_read_it(self):
        other = User.objects.create_user("other@example.org", self.institution, "1234")
        self.client.force_login(other)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("image", response.get("Content-Type", ""))

    def test_payload_carries_server_url_and_token(self):
        from django.test import RequestFactory

        from user.views import TokenQRView

        request = RequestFactory().get("/")
        payload = json.loads(TokenQRView.payload(request, self.token))

        self.assertEqual(payload["url"], "http://testserver/")
        self.assertEqual(payload["token"], str(self.token.token))

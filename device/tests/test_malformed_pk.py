from django.test import TestCase, Client
from django.urls import reverse

from user.models import Institution, User


class MalformedDeviceIdTests(TestCase):
    """A device id is "<algorithm>:<hid>"; without the colon Device() used to
    blow up while splitting instead of answering 404."""

    malformed = "nocolonhere"

    def setUp(self):
        self.client = Client()
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create_user(
            email="u@example.com",
            institution=self.institution,
            password="testpass123",
        )

    def test_details_view_returns_404(self):
        self.client.login(username="u@example.com", password="testpass123")
        response = self.client.get(
            reverse("device:details", kwargs={"pk": self.malformed}))
        self.assertEqual(response.status_code, 404)

    def test_public_view_returns_404(self):
        response = self.client.get(
            reverse("device:device_web", kwargs={"pk": self.malformed}))
        self.assertEqual(response.status_code, 404)

    def test_public_json_view_returns_404(self):
        response = self.client.get(
            reverse("device:device_web", kwargs={"pk": self.malformed}),
            headers={"accept": "application/json"},
        )
        self.assertEqual(response.status_code, 404)

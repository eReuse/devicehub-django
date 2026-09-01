from django.test import TestCase, Client
from django.urls import reverse

from action.models import State, StateDefinition
from user.models import Institution, User


class BulkStateChangeInstitutionScopeTests(TestCase):
    """The state to apply comes straight from the url, so it has to be
    resolved inside the user's institution."""

    def setUp(self):
        self.client = Client()
        self.institution = Institution.objects.create(name="Mine")
        self.user = User.objects.create_user(
            email="mine@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.client.login(username="mine@example.com", password="testpass123")

        self.other_institution = Institution.objects.create(name="Theirs")
        self.their_state = StateDefinition.objects.create(
            institution=self.other_institution, state="Refurbished"
        )

    def url_for(self, pk):
        return reverse("action:bulk_change_state", kwargs={"pk": pk})

    def get(self, pk):
        # the view redirects back to the referer, which a browser always sends
        return self.client.get(self.url_for(pk), HTTP_REFERER="/dashboard/")

    def test_state_from_another_institution_returns_404(self):
        response = self.client.get(self.url_for(self.their_state.pk))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(State.objects.exists())

    def test_unknown_state_returns_404(self):
        response = self.client.get(self.url_for(self.their_state.pk + 100))
        self.assertEqual(response.status_code, 404)

    def test_own_state_is_accepted(self):
        state = StateDefinition.objects.create(
            institution=self.institution, state="Refurbished"
        )
        response = self.get(state.pk)
        self.assertEqual(response.status_code, 302)

    def test_redirects_to_the_dashboard_without_a_referer(self):
        state = StateDefinition.objects.create(
            institution=self.institution, state="Repaired"
        )
        response = self.client.get(self.url_for(state.pk))
        self.assertRedirects(response, reverse("dashboard:all_device"))

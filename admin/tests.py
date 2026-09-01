from django.test import TestCase, Client
from django.urls import reverse

from action.models import StateDefinition
from lot.models import LotTag
from user.models import Institution, User


class OrderingInstitutionScopeTests(TestCase):
    """The reordering views take a list of ids from the form, so every id has
    to be resolved inside the user's institution."""

    def setUp(self):
        self.client = Client()
        self.institution = Institution.objects.create(name="Mine")
        self.user = User.objects.create_superuser(
            email="mine@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.client.login(username="mine@example.com", password="testpass123")

        # the inbox tag is skipped by the view, keep it out of the fixtures
        LotTag.objects.create(
            name="Inbox", owner=self.institution, inbox=True)
        self.tag_a = LotTag.objects.create(name="A", owner=self.institution)
        self.tag_b = LotTag.objects.create(name="B", owner=self.institution)
        self.state_a = StateDefinition.objects.create(
            institution=self.institution, state="A")
        self.state_b = StateDefinition.objects.create(
            institution=self.institution, state="B")

        self.other_institution = Institution.objects.create(name="Theirs")
        self.their_tag = LotTag.objects.create(
            name="T", owner=self.other_institution)
        self.their_state = StateDefinition.objects.create(
            institution=self.other_institution, state="T")

    def post_tag_order(self, *ids):
        return self.client.post(
            reverse("admin:update_lot_tag_order"),
            {"ordering": ",".join(str(i) for i in ids)},
        )

    def post_state_order(self, *ids):
        return self.client.post(
            reverse("admin:update_state_order"),
            {"ordering": ",".join(str(i) for i in ids)},
        )

    def test_foreign_lot_tag_returns_404(self):
        order = self.their_tag.order
        response = self.post_tag_order(self.their_tag.pk)
        self.assertEqual(response.status_code, 404)
        self.their_tag.refresh_from_db()
        self.assertEqual(self.their_tag.order, order)

    def test_foreign_lot_tag_rolls_back_the_whole_reorder(self):
        order = self.tag_b.order
        response = self.post_tag_order(self.tag_b.pk, self.their_tag.pk)
        self.assertEqual(response.status_code, 404)
        self.tag_b.refresh_from_db()
        self.assertEqual(self.tag_b.order, order)

    def test_lot_tag_order_without_ordering_field_returns_404(self):
        response = self.client.post(reverse("admin:update_lot_tag_order"), {})
        self.assertEqual(response.status_code, 404)

    def test_own_lot_tags_are_reordered(self):
        response = self.post_tag_order(self.tag_b.pk, self.tag_a.pk)
        self.assertEqual(response.status_code, 302)
        self.tag_a.refresh_from_db()
        self.tag_b.refresh_from_db()
        self.assertLess(self.tag_b.order, self.tag_a.order)

    def test_foreign_state_definition_returns_404(self):
        order = self.their_state.order
        response = self.post_state_order(self.their_state.pk)
        self.assertEqual(response.status_code, 404)
        self.their_state.refresh_from_db()
        self.assertEqual(self.their_state.order, order)

    def test_foreign_state_definition_rolls_back_the_whole_reorder(self):
        order = self.state_b.order
        response = self.post_state_order(self.state_b.pk, self.their_state.pk)
        self.assertEqual(response.status_code, 404)
        self.state_b.refresh_from_db()
        self.assertEqual(self.state_b.order, order)

    def test_state_order_without_ordering_field_returns_404(self):
        response = self.client.post(reverse("admin:update_state_order"), {})
        self.assertEqual(response.status_code, 404)

    def test_own_state_definitions_are_reordered(self):
        response = self.post_state_order(self.state_b.pk, self.state_a.pk)
        self.assertEqual(response.status_code, 302)
        self.state_a.refresh_from_db()
        self.state_b.refresh_from_db()
        self.assertLess(self.state_b.order, self.state_a.order)

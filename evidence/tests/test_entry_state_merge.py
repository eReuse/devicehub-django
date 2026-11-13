import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from action.models import State, StateDefinition
from evidence.models import RootAlias, SystemProperty
from evidence.parse import Build
from evidence.tests.test_mobile_snapshot import mobile_snapshot
from user.models import Institution, User


class EntryStateMergeTests(TestCase):
    """A product that has moved on keeps its state when another evidence joins it."""

    def setUp(self):
        self.inst = Institution.objects.create(name="T", country="ES")
        self.user = User.objects.create_user("u@example.org", self.inst, "1234")
        # The institution comes with INBOX (order 1); name the states as lab6 does.
        StateDefinition.objects.filter(institution=self.inst, order=1).update(state="Entrada")
        for order, name in enumerate(["Per-revisar", "Per-donació"], 2):
            StateDefinition.objects.create(institution=self.inst, order=order, state=name)

    def register_with_form(self, label):
        """What the web form stores: one evidence linked to the label's product."""
        ev = uuid.uuid4()
        value = f"web24:{ev}"
        SystemProperty.objects.create(owner=self.inst, user=self.user, uuid=ev, key="web24", value=value)
        RootAlias.set_alias(self.inst, value, f"custom_id:{label}", user=self.user)
        return ev

    def set_state(self, ev, name):
        later = timezone.now() + timedelta(seconds=State.objects.count() + 1)
        state = State.objects.create(snapshot_uuid=ev, state=name, user=self.user, institution=self.inst)
        State.objects.filter(pk=state.pk).update(date=later)

    def current(self):
        return State.objects.order_by("-date").first().state

    def test_new_product_gets_entry_state(self):
        Build(mobile_snapshot("0099"), self.user)
        self.assertEqual(self.current(), "Entrada")

    def test_workbench_does_not_send_product_back_to_entry(self):
        ev = self.register_with_form("0042")
        self.set_state(ev, "Per-donació")

        Build(mobile_snapshot("0042"), self.user)

        self.assertEqual(self.current(), "Per-donació")
        self.assertEqual(State.objects.filter(state="Entrada").count(), 1)

    def test_both_sides_moved_on_keep_both_histories(self):
        ev = self.register_with_form("0042")
        self.set_state(ev, "Per-donació")
        other = uuid.uuid4()
        SystemProperty.objects.create(owner=self.inst, user=self.user, uuid=other, key="web24", value="web24:other")
        self.set_state(other, "Per-revisar")

        RootAlias.set_alias(self.inst, "web24:other", "custom_id:0042", user=self.user)

        self.assertEqual(State.objects.count(), 4)


class InstitutionWithoutStatesTests(TestCase):
    """Institutions created before INBOX existed may have no state definitions."""

    def test_new_product_without_state_definitions_does_not_crash(self):
        inst = Institution.objects.create(name="Old", country="ES")
        user = User.objects.create_user("old@example.org", inst, "1234")
        # bypass the post_delete signal that would recreate INBOX
        StateDefinition.objects.filter(institution=inst)._raw_delete("default")

        Build(mobile_snapshot("0077"), user)

        self.assertTrue(SystemProperty.objects.filter(owner=inst).exists())
        self.assertFalse(State.objects.filter(institution=inst).exists())

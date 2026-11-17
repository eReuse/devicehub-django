
import uuid
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from user.models import Institution, User
from evidence.models import SystemProperty, RootAlias
from action.models import StateDefinition, State
from device.models import Device

class StateManagementTests(TestCase):

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Org")

        self.admin = User.objects.create_user(
            email="admin@test.com",
            institution=self.institution,
            password="pass"
        )
        self.admin.is_admin = True
        self.admin.save()

        self.client = Client()
        self.client.login(username="admin@test.com", password="pass")

    def test_correct_institution_erasure(self):
        """
        Validate that cascade delete of states works properly and insitution deletion has no issues
        """
        self.assertTrue(StateDefinition.objects.filter(institution=self.institution).exists())
        Institution.objects.filter(id=self.institution.id).delete()

        self.assertFalse(Institution.objects.filter(id=self.institution.id).exists())
        self.assertFalse(StateDefinition.objects.filter(institution=self.institution).exists())

    def test_disallow_delete_last_state(self):
        """
        Validate that delete state view wont allow deletion of last state
        """
        state_def = StateDefinition.objects.get(institution=self.institution)
        self.assertEqual(StateDefinition.objects.filter(institution=self.institution).count(), 1)

        url = reverse('admin:delete_state_definition', kwargs={'pk': state_def.pk})
        response = self.client.post(url)

        self.assertRedirects(response, reverse('admin:states_panel'))
        self.assertEqual(StateDefinition.objects.filter(institution=self.institution).count(), 1)

    def test_new_evidence_doesnt_override_old_state(self):
        """
        Validate that last "inbox" state is ignored when aliasing two evidences
        """
        inbox_def = StateDefinition.objects.get(institution=self.institution)
        repair_def = StateDefinition.objects.create(
            institution=self.institution,
            state="REPAIR",
            order=2
        )

        uuid_old = uuid.uuid4()
        uuid_new = uuid.uuid4()

        # create fake evidence
        SystemProperty.objects.create(owner=self.institution, uuid=uuid_old, value="alias:viejo")

        # set artifial old date and repair state
        State.objects.filter(snapshot_uuid=uuid_old).update(
            state=repair_def.state,
            date=timezone.now() - timedelta(days=2)
        )

        # new evidence with actual date and inbox as state
        SystemProperty.objects.create(owner=self.institution, uuid=uuid_new, value="alias:nuevo")

        # aliasing
        RootAlias.set_alias(self.institution, "alias:nuevo", "alias:viejo")

        device = Device(id="alias:viejo", owner=self.institution)
        current_state = device.get_current_state()

        self.assertIsNotNone(current_state)
        self.assertEqual(current_state.state, "REPAIR")

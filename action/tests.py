from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import RestrictedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from action.management.commands.create_default_states import DEFAULT_STATES
from action.models import INITIAL_STATE, DeviceLog, State, StateDefinition
from evidence.models import RootAlias, SystemProperty
from user.models import Institution, User


class InitialStateTests(TestCase):

    def states(self, institution):
        return list(
            StateDefinition.objects.filter(institution=institution)
            .order_by('order').values_list('state', 'order')
        )

    def test_add_institution_creates_only_initial_state(self):
        call_command('add_institution', 'inst')
        institution = Institution.objects.get(name='inst')
        self.assertEqual(self.states(institution), [(INITIAL_STATE, 1)])

    def test_default_states_go_after_initial_state(self):
        call_command('add_institution', 'inst')
        institution = Institution.objects.get(name='inst')
        call_command('create_default_states', 'inst')
        expected = [(INITIAL_STATE, 1)] + [
            (state, order) for order, (state, _description) in enumerate(DEFAULT_STATES, start=2)
        ]
        self.assertEqual(self.states(institution), expected)

    def test_create_default_states_is_idempotent(self):
        call_command('add_institution', 'inst')
        institution = Institution.objects.get(name='inst')
        call_command('create_default_states', 'inst')
        before = self.states(institution)
        call_command('create_default_states', 'inst')
        self.assertEqual(self.states(institution), before)

    def test_create_default_states_unknown_institution(self):
        # Used to crash with AttributeError on institution.name
        call_command('create_default_states', 'missing')
        self.assertFalse(StateDefinition.objects.exists())


class StateModelTests(TestCase):

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        self.inbox = StateDefinition.objects.create(
            institution=self.institution, state=INITIAL_STATE)
        self.repair = StateDefinition.objects.create(
            institution=self.institution, state='REPAIR')

    def test_one_row_per_root(self):
        State.objects.create(
            institution=self.institution, root='ereuse24:a', state_definition=self.inbox)
        with self.assertRaises(IntegrityError):
            State.objects.create(
                institution=self.institution, root='ereuse24:a', state_definition=self.repair)

    def test_state_definition_must_belong_to_institution(self):
        other = Institution.objects.create(name='other')
        with self.assertRaises(ValidationError):
            State.objects.create(
                institution=other, root='ereuse24:a', state_definition=self.inbox)

    def test_state_definition_in_use_cannot_be_deleted(self):
        State.objects.create(
            institution=self.institution, root='ereuse24:a', state_definition=self.repair)
        with self.assertRaises(RestrictedError):
            self.repair.delete()

    def test_state_definition_not_in_use_can_be_deleted(self):
        State.objects.create(
            institution=self.institution, root='ereuse24:a', state_definition=self.inbox)
        self.repair.delete()
        self.assertFalse(StateDefinition.objects.filter(pk=self.repair.pk).exists())

    def test_deleting_institution_cascades(self):
        State.objects.create(
            institution=self.institution, root='ereuse24:a', state_definition=self.repair)
        self.institution.delete()
        self.assertFalse(State.objects.exists())
        self.assertFalse(StateDefinition.objects.exists())


class InitialStateOnNewDeviceTests(TestCase):
    """A new root (first SystemProperty of a value) gets its initial State."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        StateDefinition.objects.create(institution=self.institution, state='FIRST')
        StateDefinition.objects.create(institution=self.institution, state='SECOND')

    def evidence(self, value, uuid=None):
        uuid = uuid or uuid4()
        SystemProperty.objects.create(
            owner=self.institution, key='ereuse24', value=value, uuid=uuid)
        return uuid

    def test_new_device_gets_first_state_and_log(self):
        uuid = self.evidence('ereuse24:a')
        state = State.objects.get(institution=self.institution, root='ereuse24:a')
        self.assertEqual(state.state_definition.state, 'FIRST')
        logs = DeviceLog.objects.filter(institution=self.institution, snapshot_uuid=uuid)
        self.assertEqual(logs.count(), 1)
        self.assertIn("'FIRST'", logs.first().event)

    def test_new_evidence_of_known_device_keeps_its_state(self):
        self.evidence('ereuse24:a')
        second = StateDefinition.objects.get(institution=self.institution, state='SECOND')
        State.objects.filter(root='ereuse24:a').update(state_definition=second)
        uuid = self.evidence('ereuse24:a')
        self.assertEqual(State.objects.filter(root='ereuse24:a').count(), 1)
        self.assertEqual(State.objects.get(root='ereuse24:a').state_definition, second)
        self.assertFalse(DeviceLog.objects.filter(snapshot_uuid=uuid).exists())

    def test_institution_without_states_gets_initial_state(self):
        bare = Institution.objects.create(name='bare')
        SystemProperty.objects.create(
            owner=bare, key='ereuse24', value='ereuse24:b', uuid=uuid4())
        state = State.objects.get(institution=bare, root='ereuse24:b')
        self.assertEqual(state.state_definition.state, INITIAL_STATE)
        self.assertEqual(StateDefinition.objects.filter(institution=bare).count(), 1)


class StateFollowsRerootTests(TestCase):
    """RootAlias.set_alias keeps one State row per alias and per root."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        self.inbox = StateDefinition.objects.create(institution=self.institution, state='INBOX')
        self.repair = StateDefinition.objects.create(institution=self.institution, state='REPAIR')
        self.test = StateDefinition.objects.create(institution=self.institution, state='TEST')
        for value in ('ereuse24:a', 'ereuse24:b'):
            SystemProperty.objects.create(
                owner=self.institution, key='ereuse24', value=value, uuid=uuid4())

    def set_state(self, root, state_def, minutes_ago):
        State.objects.filter(institution=self.institution, root=root).update(
            state_definition=state_def,
            date=timezone.now() - timedelta(minutes=minutes_ago))

    def state(self, root):
        return State.objects.get(institution=self.institution, root=root).state_definition

    def set_alias(self, alias, root):
        RootAlias.set_alias(self.institution, alias, root)

    def test_merge_newest_state_wins_and_alias_row_stays(self):
        self.set_state('ereuse24:a', self.repair, minutes_ago=1)
        self.set_state('ereuse24:b', self.test, minutes_ago=10)
        self.set_alias('ereuse24:a', 'ereuse24:b')
        self.assertEqual(self.state('ereuse24:b'), self.repair)
        self.assertEqual(self.state('ereuse24:a'), self.repair)   # dormant

    def test_merge_older_state_loses(self):
        self.set_state('ereuse24:a', self.repair, minutes_ago=10)
        self.set_state('ereuse24:b', self.test, minutes_ago=1)
        self.set_alias('ereuse24:a', 'ereuse24:b')
        self.assertEqual(self.state('ereuse24:b'), self.test)
        self.assertEqual(self.state('ereuse24:a'), self.repair)   # dormant

    def test_split_restores_previous_state(self):
        self.set_state('ereuse24:a', self.repair, minutes_ago=10)
        self.set_state('ereuse24:b', self.test, minutes_ago=1)
        self.set_alias('ereuse24:a', 'ereuse24:b')
        self.set_alias('ereuse24:a', 'ereuse24:a')
        self.assertEqual(self.state('ereuse24:a'), self.repair)
        self.assertEqual(self.state('ereuse24:b'), self.test)
        self.assertTrue(DeviceLog.objects.filter(event__contains='restored').exists())

    def test_fresh_custom_id_copies_state(self):
        self.set_state('ereuse24:a', self.repair, minutes_ago=1)
        self.set_alias('ereuse24:a', 'custom_id:x')
        self.assertEqual(self.state('custom_id:x'), self.repair)
        self.assertEqual(self.state('ereuse24:a'), self.repair)

    def test_custom_id_without_aliases_is_dropped(self):
        self.set_alias('ereuse24:a', 'custom_id:x')
        self.set_alias('ereuse24:a', 'custom_id:y')
        self.assertFalse(State.objects.filter(root='custom_id:x').exists())
        self.assertTrue(State.objects.filter(root='custom_id:y').exists())

    def test_custom_id_with_other_aliases_is_kept(self):
        self.set_alias('ereuse24:a', 'custom_id:x')
        self.set_alias('ereuse24:b', 'custom_id:x')
        self.set_alias('ereuse24:a', 'ereuse24:a')
        self.assertTrue(State.objects.filter(root='custom_id:x').exists())

    def test_every_alias_and_root_has_one_row(self):
        self.set_alias('ereuse24:a', 'custom_id:x')
        self.set_alias('ereuse24:b', 'custom_id:x')
        self.set_alias('ereuse24:a', 'ereuse24:a')
        expected = set(RootAlias.objects.values_list('alias', flat=True)) | set(
            RootAlias.objects.values_list('root', flat=True))
        self.assertEqual(set(State.objects.values_list('root', flat=True)), expected)


class StateChangeViewsTests(TestCase):
    """Writers update the root's row in place and log the change."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        self.user = User.objects.create_user(
            email='u@test.local', institution=self.institution, password='pass1234')
        self.client.login(email='u@test.local', password='pass1234')
        self.inbox = StateDefinition.objects.create(institution=self.institution, state='INBOX')
        self.repair = StateDefinition.objects.create(institution=self.institution, state='REPAIR')
        self.uuid_a = uuid4()
        SystemProperty.objects.create(
            owner=self.institution, key='ereuse24', value='ereuse24:a', uuid=self.uuid_a)
        SystemProperty.objects.create(
            owner=self.institution, key='ereuse24', value='ereuse24:b', uuid=uuid4())
        # a is an alias of b: the state must land on the root b.
        RootAlias.set_alias(self.institution, 'ereuse24:a', 'ereuse24:b')

    def state(self, root):
        return State.objects.get(institution=self.institution, root=root).state_definition

    def test_change_state_updates_root_row(self):
        self.client.post(reverse('action:change_state'), {
            'previous_state': 'INBOX', 'new_state': 'REPAIR',
            'snapshot_uuid': self.uuid_a, 'device_id': 'ereuse24:a',
        })
        self.assertEqual(self.state('ereuse24:b'), self.repair)
        self.assertEqual(self.state('ereuse24:a'), self.inbox)   # dormant, untouched
        self.assertEqual(State.objects.filter(root='ereuse24:b').count(), 1)
        self.assertTrue(DeviceLog.objects.filter(
            snapshot_uuid=self.uuid_a, event__contains="'REPAIR'").exists())

    def test_change_state_unknown_name_changes_nothing(self):
        self.client.post(reverse('action:change_state'), {
            'previous_state': 'INBOX', 'new_state': 'NOPE',
            'snapshot_uuid': self.uuid_a, 'device_id': 'ereuse24:b',
        })
        self.assertEqual(self.state('ereuse24:b'), self.inbox)

    def test_bulk_change_state(self):
        self.client.post(
            reverse('action:bulk_change_state', args=[self.repair.pk]),
            {'devices': ['ereuse24:b']}, HTTP_REFERER='/')
        self.assertEqual(self.state('ereuse24:b'), self.repair)

    def test_bulk_change_state_rejects_other_institution_state(self):
        other = Institution.objects.create(name='other')
        foreign = StateDefinition.objects.create(institution=other, state='FOREIGN')
        self.client.post(
            reverse('action:bulk_change_state', args=[foreign.pk]),
            {'devices': ['ereuse24:b']})
        self.assertEqual(self.state('ereuse24:b'), self.inbox)

    def test_bulk_without_referer_or_devices_redirects_to_dashboard(self):
        response = self.client.post(
            reverse('action:bulk_change_state', args=[self.repair.pk]))
        self.assertRedirects(
            response, reverse('dashboard:unassigned'), fetch_redirect_response=False)


class DeleteStateDefinitionTests(TestCase):
    """Deleting a state reassigns every row using it, dormant ones too."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        self.admin = User.objects.create_user(
            email='admin@test.local', institution=self.institution, password='pass1234')
        self.admin.is_admin = True
        self.admin.save()
        self.client.login(email='admin@test.local', password='pass1234')
        self.inbox = StateDefinition.objects.create(institution=self.institution, state='INBOX')
        self.repair = StateDefinition.objects.create(institution=self.institution, state='REPAIR')
        self.test = StateDefinition.objects.create(institution=self.institution, state='TEST')
        for value in ('ereuse24:a', 'ereuse24:b'):
            SystemProperty.objects.create(
                owner=self.institution, key='ereuse24', value=value, uuid=uuid4())

    def set_state(self, root, state_def):
        State.objects.filter(institution=self.institution, root=root).update(
            state_definition=state_def)

    def state(self, root):
        return State.objects.get(institution=self.institution, root=root).state_definition

    def make_dormant_repair(self):
        # a is in REPAIR, then merged into b (newer TEST wins): only the
        # dormant row of a keeps REPAIR.
        self.set_state('ereuse24:a', self.repair)
        State.objects.filter(root='ereuse24:a').update(
            date=timezone.now() - timedelta(minutes=10))
        State.change(self.institution, 'ereuse24:b', self.test)
        RootAlias.set_alias(self.institution, 'ereuse24:a', 'ereuse24:b')

    def test_product_counts_ignore_dormant_rows(self):
        self.make_dormant_repair()
        counts = StateDefinition.product_counts(self.institution)
        self.assertEqual(counts.get(self.repair.pk, 0), 0)
        self.assertEqual(counts[self.test.pk], 1)

    def test_only_dormant_rows_go_to_first_other_state(self):
        self.make_dormant_repair()
        target, moved = self.repair.delete_reassigning()
        self.assertEqual((target, moved), (self.inbox, 1))
        self.assertEqual(self.state('ereuse24:a'), self.inbox)
        # split: a gets the state its dormant row was moved to
        RootAlias.set_alias(self.institution, 'ereuse24:a', 'ereuse24:a')
        self.assertEqual(self.state('ereuse24:a'), self.inbox)

    def test_first_state_dormant_rows_go_to_next(self):
        # a keeps INBOX (older) and is merged into b (TEST): INBOX is only
        # used by a's dormant row, so it goes to the next state by order.
        State.objects.filter(root='ereuse24:a').update(
            date=timezone.now() - timedelta(minutes=10))
        State.change(self.institution, 'ereuse24:b', self.test)
        RootAlias.set_alias(self.institution, 'ereuse24:a', 'ereuse24:b')
        target, moved = self.inbox.delete_reassigning()
        self.assertEqual((target, moved), (self.repair, 1))
        self.assertEqual(self.state('ereuse24:a'), self.repair)

    def test_visible_products_need_a_target(self):
        self.set_state('ereuse24:a', self.repair)
        with self.assertRaises(ValidationError):
            self.repair.delete_reassigning()
        self.repair.delete_reassigning(self.test)
        self.assertEqual(self.state('ereuse24:a'), self.test)

    def test_target_from_other_institution_is_refused(self):
        other = Institution.objects.create(name='other')
        foreign = StateDefinition.objects.create(institution=other, state='FOREIGN')
        with self.assertRaises(ValidationError):
            self.repair.delete_reassigning(foreign)

    def test_last_state_cannot_be_deleted(self):
        bare = Institution.objects.create(name='bare')
        only = StateDefinition.objects.create(institution=bare, state='ONLY')
        with self.assertRaises(ValidationError):
            only.delete_reassigning()
        self.assertTrue(StateDefinition.objects.filter(pk=only.pk).exists())

    def test_view_moves_products_to_chosen_target(self):
        self.set_state('ereuse24:a', self.repair)
        self.client.post(
            reverse('admin:delete_state_definition', args=[self.repair.pk]),
            {'target': self.test.pk})
        self.assertFalse(StateDefinition.objects.filter(pk=self.repair.pk).exists())
        self.assertEqual(self.state('ereuse24:a'), self.test)

    def test_view_without_target_keeps_state_in_use(self):
        self.set_state('ereuse24:a', self.repair)
        self.client.post(
            reverse('admin:delete_state_definition', args=[self.repair.pk]))
        self.assertTrue(StateDefinition.objects.filter(pk=self.repair.pk).exists())
        self.assertEqual(self.state('ereuse24:a'), self.repair)

    def test_panel_shows_product_counts(self):
        self.set_state('ereuse24:a', self.repair)
        response = self.client.get(reverse('admin:states_panel'))
        counts = {sd.state: sd.product_count for sd in response.context['state_definitions']}
        self.assertEqual(counts, {'INBOX': 1, 'REPAIR': 1, 'TEST': 0})


class StateOrderViewTests(TestCase):
    """UpdateStateOrderView only reorders the institution's full state list."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        admin = User.objects.create_user(
            email='admin@test.local', institution=self.institution, password='pass1234')
        admin.is_admin = True
        admin.save()
        self.client.login(email='admin@test.local', password='pass1234')
        self.a = StateDefinition.objects.create(institution=self.institution, state='A')
        self.b = StateDefinition.objects.create(institution=self.institution, state='B')
        other = Institution.objects.create(name='other')
        self.foreign = StateDefinition.objects.create(institution=other, state='FOREIGN')

    def order(self):
        return list(StateDefinition.objects.filter(institution=self.institution)
                    .order_by('order').values_list('state', flat=True))

    def post(self, ids):
        self.client.post(reverse('admin:update_state_order'),
                         {'ordering': ','.join(str(i) for i in ids)})

    def test_full_list_reorders(self):
        self.post([self.b.pk, self.a.pk])
        self.assertEqual(self.order(), ['B', 'A'])

    def test_foreign_ids_are_refused(self):
        self.post([self.b.pk, self.foreign.pk])
        self.assertEqual(self.order(), ['A', 'B'])
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.order, 1)

    def test_partial_or_repeated_list_is_refused(self):
        self.post([self.b.pk])
        self.assertEqual(self.order(), ['A', 'B'])
        self.post([self.b.pk, self.b.pk])
        self.assertEqual(self.order(), ['A', 'B'])


class StateReadersTests(TestCase):
    """Readers resolve the product's root: aliases never show their own row."""

    def setUp(self):
        self.institution = Institution.objects.create(name='inst')
        self.user = User.objects.create_user(
            email='u@test.local', institution=self.institution, password='pass1234')
        self.client.login(email='u@test.local', password='pass1234')
        self.inbox = StateDefinition.objects.create(institution=self.institution, state='INBOX')
        self.repair = StateDefinition.objects.create(institution=self.institution, state='REPAIR')
        for value in ('ereuse24:a', 'ereuse24:b'):
            SystemProperty.objects.create(
                owner=self.institution, key='ereuse24', value=value, uuid=uuid4())
        # a (REPAIR, older) merged into b (INBOX, newer): b shows INBOX and
        # a's dormant row keeps REPAIR.
        State.objects.filter(root='ereuse24:a').update(
            state_definition=self.repair, date=timezone.now() - timedelta(minutes=10))
        RootAlias.set_alias(self.institution, 'ereuse24:a', 'ereuse24:b')

    def test_device_get_current_state_uses_root(self):
        from device.models import Device
        device = Device(id='ereuse24:a', owner=self.institution)
        self.assertEqual(device.get_current_state().state_definition, self.inbox)
        # Built without owner (as the bulk view does): the owner comes from
        # the evidence later, and the root must still be resolved.
        no_owner = Device(id='ereuse24:a')
        no_owner.owner = self.institution
        self.assertEqual(no_owner.get_current_state().state_definition, self.inbox)

    def test_current_by_root(self):
        self.assertEqual(
            State.current_by_root(self.institution, ['ereuse24:b']),
            {'ereuse24:b': 'INBOX'})

    def test_overview_counts_live_roots_only(self):
        from device.product_cache import ProductCache
        roots = set(ProductCache.objects.filter(owner=self.institution)
                    .values_list('root', flat=True))
        response = self.client.get(reverse('dashboard:overview'))
        summary = {s['state']: s['count'] for s in response.context['states_summary']}
        # Only live roots listed in ProductCache are counted; the dormant
        # REPAIR row of a never shows up.
        self.assertNotIn('REPAIR', summary)
        self.assertEqual(sum(summary.values()), len(roots))


class StateDataMigrationTests(TransactionTestCase):
    """0005: legacy snapshot_uuid rows -> one row per root/alias."""

    before = [("action", "0004_state_root_state_definition"),
              ("evidence", "0013_credentialproperty_and_more")]
    after = [("action", "0006_state_finalize")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        # Back to the latest schema, not just ``after``: later migrations
        # (0007 onwards) must be applied for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_migration(self):
        apps = self.migrate(self.before)
        Institution = apps.get_model("user", "Institution")
        StateDefinition = apps.get_model("action", "StateDefinition")
        State = apps.get_model("action", "State")
        SystemProperty = apps.get_model("evidence", "SystemProperty")
        RootAlias = apps.get_model("evidence", "RootAlias")

        inst = Institution.objects.create(name="inst")
        empty = Institution.objects.create(name="empty")
        StateDefinition.objects.create(institution=inst, state="INBOX", order=1)
        StateDefinition.objects.create(institution=inst, state="REPAIR", order=2)
        StateDefinition.objects.create(institution=inst, state="TEST", order=3)

        def device(value, root=None, uuid=None):
            uuid = uuid or uuid4()
            SystemProperty.objects.create(owner=inst, key="ereuse24", value=value, uuid=uuid)
            RootAlias.objects.create(owner=inst, alias=value, root=root or value,
                                     updated=timezone.now())
            return uuid

        def legacy(name, uuid, minutes, institution=inst):
            st = State.objects.create(institution=institution, state=name, snapshot_uuid=uuid)
            State.objects.filter(pk=st.pk).update(
                date=timezone.now() - timedelta(minutes=minutes))

        u_root = device("ereuse24:b")              # root B
        u_alias = device("ereuse24:a", "ereuse24:b")  # A merged into B
        device("ereuse24:c")                       # no legacy state
        u_custom = device("ereuse24:d", "custom_id:x")  # root without own row

        legacy("REPAIR", u_alias, minutes=10)
        legacy("TEST", u_root, minutes=5)           # newest for root B
        legacy("TEST", u_custom, minutes=1)
        legacy("GONE", u_root, minutes=1)           # unknown name -> ignored
        legacy("REPAIR", uuid4(), minutes=1)        # unresolved uuid
        legacy("REPAIR", u_root, minutes=1, institution=None)

        apps = self.migrate(self.after)
        State = apps.get_model("action", "State")
        StateDefinition = apps.get_model("action", "StateDefinition")

        got = {
            (s.institution.name, s.root): s.state_definition.state
            for s in State.objects.select_related("institution", "state_definition")
        }
        self.assertEqual(got, {
            ("inst", "ereuse24:b"): "TEST",       # newest of A and B wins
            ("inst", "ereuse24:a"): "REPAIR",     # dormant, its own state
            ("inst", "ereuse24:c"): "INBOX",      # default (first by order)
            ("inst", "custom_id:x"): "TEST",
            ("inst", "ereuse24:d"): "TEST",       # dormant
        })
        self.assertEqual(
            list(StateDefinition.objects.filter(institution__name="empty")
                 .values_list("state", "order")),
            [("INBOX", 1)],
        )

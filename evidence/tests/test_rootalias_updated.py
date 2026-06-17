import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from user.models import Institution
from device.models import Device
from evidence.models import SystemProperty, RootAlias, ensure_root_alias_self_reference


class RootAliasUpdatedSignalTests(TestCase):
    """``ensure_root_alias_self_reference`` must seed ``created`` and
    ``updated`` from the first SystemProperty and bump only ``updated``
    on subsequent ones (monotonic, never regresses).
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value=value,
        )

    def test_signal_creates_row_with_sp_created_as_created_and_updated(self):
        sp = self._sp("ereuse24:a1")
        ra = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        self.assertEqual(ra.created, sp.created)
        self.assertEqual(ra.updated, sp.created)

    def test_second_sp_bumps_updated_only(self):
        self._sp("ereuse24:a1")
        ra0 = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        original_created = ra0.created

        sp2 = self._sp("ereuse24:a1")
        ra1 = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")

        self.assertEqual(ra1.updated, sp2.created)
        self.assertEqual(ra1.created, original_created)

    def test_second_sp_does_not_bump_created(self):
        sp1 = self._sp("ereuse24:a1")
        self._sp("ereuse24:a1")
        ra = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        self.assertEqual(ra.created, sp1.created)

    def test_older_sp_does_not_regress_updated(self):
        self._sp("ereuse24:a1")
        # Create a second SP so updated is bumped; capture the resulting max.
        sp_old = SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value="ereuse24:a1",
        )
        newest = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1").updated

        # Backdate the SP and re-emit the signal: the guard must not regress updated.
        past = newest - timedelta(days=7)
        SystemProperty.objects.filter(pk=sp_old.pk).update(created=past)
        sp_old.refresh_from_db()
        ensure_root_alias_self_reference(
            sender=SystemProperty, instance=sp_old, created=True,
        )

        ra1 = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        self.assertEqual(ra1.updated, newest)


class RootAliasSetAliasTimestampTests(TestCase):
    """``set_alias`` updates ``root``/``user`` but must never touch
    ``created`` or ``updated`` of an existing row.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value=value,
        )

    def test_set_alias_does_not_modify_updated(self):
        self._sp("ereuse24:a1")
        self._sp("ereuse24:a2")
        before = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        updated_before = before.updated

        RootAlias.set_alias(self.institution, "ereuse24:a1", "ereuse24:a2")

        after = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        self.assertEqual(after.updated, updated_before)

    def test_set_alias_does_not_modify_created(self):
        self._sp("ereuse24:a1")
        self._sp("ereuse24:a2")
        before = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        created_before = before.created

        RootAlias.set_alias(self.institution, "ereuse24:a1", "ereuse24:a2")

        after = RootAlias.objects.get(owner=self.institution, alias="ereuse24:a1")
        self.assertEqual(after.created, created_before)


class RootsQuerysetOrderingTests(TestCase):
    """``Device._roots_queryset`` orders roots by ``MAX(updated)`` DESC."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Test")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value=value,
        )

    def _set_updated(self, alias, ts):
        RootAlias.objects.filter(
            owner=self.institution, alias=alias,
        ).update(updated=ts)

    def test_roots_queryset_orders_by_latest_updated_desc(self):
        self._sp("ereuse24:a1")
        self._sp("ereuse24:b1")
        self._sp("ereuse24:c1")

        now = timezone.now()
        self._set_updated("ereuse24:a1", now - timedelta(days=10))
        self._set_updated("ereuse24:b1", now - timedelta(days=1))
        self._set_updated("ereuse24:c1", now - timedelta(days=5))

        roots = [
            r["root"]
            for r in Device._roots_queryset(self.institution)
        ]
        self.assertEqual(roots, ["ereuse24:b1", "ereuse24:c1", "ereuse24:a1"])

    def test_get_all_count_matches_distinct_roots(self):
        self._sp("phid:a1")
        self._sp("phid:b1")
        self._sp("phid:c1")
        # alias phid:a1 -> phid:b1, so distinct roots are {phid:b1, phid:c1}
        RootAlias.set_alias(self.institution, "phid:a1", "phid:b1")

        devices, count = Device.get_all(self.institution)
        self.assertEqual(count, 2)
        self.assertEqual(len(devices), 2)
        self.assertEqual({d.id for d in devices}, {"phid:b1", "phid:c1"})

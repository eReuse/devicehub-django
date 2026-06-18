import uuid as uuidlib

from django.test import TestCase
from django.utils import timezone

from user.models import Institution
from evidence.models import SystemProperty, RootAlias
from device.models import ProductCache


class ProductCacheSignalTests(TestCase):
    """post_save(SystemProperty) keeps the projection in sync with evidence."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value=value)

    def test_new_evidence_creates_projection(self):
        self._sp("ereuse24:aaaaaa")
        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:aaaaaa").exists())

    def test_second_evidence_same_device_keeps_one_row(self):
        self._sp("ereuse24:aaaaaa")
        self._sp("ereuse24:aaaaaa")
        self.assertEqual(
            ProductCache.objects.filter(
                owner=self.inst, root="ereuse24:aaaaaa").count(),
            1,
        )

    def test_projection_keyed_by_canonical_root(self):
        # Pre-existing custom alias: the value resolves to a custom root, so the
        # projection must be keyed by that root, not the physical id.
        now = timezone.now()
        RootAlias.objects.create(
            owner=self.inst, alias="ereuse24:aaaaaa",
            root="custom_id:DEVICE1", created=now, updated=now)
        self._sp("ereuse24:aaaaaa")
        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="custom_id:DEVICE1").exists())
        self.assertFalse(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:aaaaaa").exists())


class ProductCacheSetAliasTests(TestCase):
    """set_alias moves the projection to follow the canonical id change."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst")

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value=value)

    def test_reassign_drops_old_root_when_last_child(self):
        self._sp("ereuse24:aaaaaa")   # device A, self-referential
        self._sp("ereuse24:bbbbbb")   # device B, target root
        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:aaaaaa").exists())

        RootAlias.set_alias(self.inst, "ereuse24:aaaaaa", "ereuse24:bbbbbb")

        # A merged into B: A was its own last child -> dropped; B rebuilt.
        self.assertFalse(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:aaaaaa").exists())
        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:bbbbbb").exists())

    def test_reroot_into_existing_projection_keeps_single_row(self):
        """Re-root collision through set_alias: both A and B already have a
        projection row. Merging A into B must leave exactly one row for B and
        none for A, with no unique(owner, root) violation."""
        self._sp("ereuse24:aaaaaa")
        self._sp("ereuse24:bbbbbb")
        self.assertEqual(ProductCache.objects.filter(
            owner=self.inst).count(), 2)

        RootAlias.set_alias(self.inst, "ereuse24:aaaaaa", "ereuse24:bbbbbb")

        self.assertEqual(
            ProductCache.objects.filter(
                owner=self.inst, root="ereuse24:bbbbbb").count(),
            1,
        )
        self.assertFalse(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:aaaaaa").exists())

    def test_reassign_keeps_old_root_when_still_canonical(self):
        self._sp("ereuse24:cccccc")   # root C
        self._sp("ereuse24:dddddd")   # alias D
        RootAlias.set_alias(self.inst, "ereuse24:dddddd", "ereuse24:cccccc")
        self._sp("ereuse24:eeeeee")   # root E

        # Move D from C to E. C still has its own self-reference -> stays.
        RootAlias.set_alias(self.inst, "ereuse24:dddddd", "ereuse24:eeeeee")

        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:cccccc").exists())
        self.assertTrue(ProductCache.objects.filter(
            owner=self.inst, root="ereuse24:eeeeee").exists())

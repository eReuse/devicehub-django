import uuid
from django.test import TestCase
from device.models import Device
from user.models import Institution
from evidence.models import SystemProperty, RootAlias
from lot.models import Lot, LotTag


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Test Institution"
        )
        i = self.institution
        for x in ["ereuse24:a1", "ereuse24:a2", "ereuse24:a3", "ereuse24:b1",
                  "ereuse24:b3", "ereuse24:c1", "ereuse24:d1", "ereuse24:d2"]:
            SystemProperty.objects.create(owner=i, uuid=uuid.uuid4(), value=x)
        alias  = [
            ("ereuse24:a1", "ereuse24:a2"),
            ("ereuse24:a3", "ereuse24:a2"),
            ("ereuse24:b1", "ereuse24:b2"),
            ("ereuse24:b3", "ereuse24:b2"),
            ("ereuse24:c1", "ereuse24:c2"),
            ("ereuse24:d1", "ereuse24:d2"),
        ]

        # Every SystemProperty already has a self-referential RootAlias row
        # created by the post_save signal; use update_or_create so that the
        # unique (owner, alias) constraint is respected when setting a real
        # alias over the pre-existing self-reference.
        for ali, root in alias:
            RootAlias.objects.update_or_create(
                owner=i, alias=ali, defaults={"root": root}
            )

    def test_queryset_all_returns_canonical_roots(self):
        """Phase 6.1 semantic: one canonical root per logical device.

        Expected roots: a2, b2, c2, d2 (four groups collapsed by alias).
        """
        result = {r["root"] for r in Device._roots_queryset(self.institution)}
        self.assertEqual(result, {"ereuse24:a2", "ereuse24:b2",
                                  "ereuse24:c2", "ereuse24:d2"})

    def test_queryset_unassigned_excludes_devices_in_lots(self):
        """Roots stored in DeviceLot must not appear as unassigned."""
        tag = LotTag.objects.create(name="default", owner=self.institution)
        lot = Lot.objects.create(
            name="lot-a", owner=self.institution, type=tag
        )
        # b2 is a canonical root with no SystemProperty row; adding any of
        # its physical aliases stores the root (Phase 2).
        lot.add("ereuse24:b1")

        result = {
            r["root"]
            for r in Device.queryset_orm_unassigned(self.institution)
        }
        self.assertEqual(result, {"ereuse24:a2", "ereuse24:c2", "ereuse24:d2"})

import uuid

from django.test import TestCase

from user.models import Institution, User
from evidence.models import SystemProperty, RootAlias
from lot.models import (
    Lot,
    LotTag,
    DeviceLot,
    Beneficiary,
    DeviceBeneficiary,
    LotSubscription,
)


class CanonicalDeviceIdsTests(TestCase):
    """Phase 2 of Option 5.

    After Phase 1 there is exactly one RootAlias row per SystemProperty.value;
    Lot.add / Beneficiary.add must store the canonical root so that physical
    variants of the same logical device collapse to a single membership row.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.user = User.objects.create(
            email="owner@test.local",
            institution=self.institution,
        )
        self.tag = LotTag.objects.create(
            name="default", owner=self.institution
        )
        self.lot = Lot.objects.create(
            name="lot-a",
            owner=self.institution,
            type=self.tag,
        )

        # Two physical aliases that share the same canonical root "ereuse24:b2".
        for v in ["ereuse24:b1", "ereuse24:b3", "ereuse24:b2"]:
            SystemProperty.objects.create(
                owner=self.institution, uuid=uuid.uuid4(), value=v
            )
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:b1",
            defaults={"root": "ereuse24:b2"},
        )
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:b3",
            defaults={"root": "ereuse24:b2"},
        )

    # --- helper ---------------------------------------------------------

    def test_resolve_root_returns_root(self):
        self.assertEqual(RootAlias.resolve_root(self.institution, "ereuse24:b1"), "ereuse24:b2")
        self.assertEqual(RootAlias.resolve_root(self.institution, "ereuse24:b3"), "ereuse24:b2")
        self.assertEqual(RootAlias.resolve_root(self.institution, "ereuse24:b2"), "ereuse24:b2")

    def test_resolve_root_falls_back_when_missing(self):
        self.assertEqual(
            RootAlias.resolve_root(self.institution, "unknown"), "unknown"
        )

    def test_physical_aliases_covers_all_siblings(self):
        self.assertEqual(
            set(RootAlias.physical_aliases(self.institution, "ereuse24:b1")),
            {"ereuse24:b1", "ereuse24:b2", "ereuse24:b3"},
        )
        # input not in RootAlias still falls back to itself
        self.assertEqual(
            set(RootAlias.physical_aliases(self.institution, "unknown")),
            {"unknown"},
        )

    # --- Lot.add --------------------------------------------------------

    def test_lot_add_with_physical_stores_root(self):
        self.lot.add("ereuse24:b1")
        self.assertEqual(
            list(DeviceLot.objects.filter(lot=self.lot).values_list(
                "device_id", flat=True
            )),
            ["ereuse24:b2"],
        )

    def test_lot_add_dedupes_physical_variants(self):
        self.lot.add("ereuse24:b1")
        self.lot.add("ereuse24:b3")
        self.lot.add("ereuse24:b2")
        self.assertEqual(
            DeviceLot.objects.filter(lot=self.lot).count(), 1
        )

    def test_lot_add_without_rootalias_stores_as_is(self):
        self.lot.add("legacy-id")
        self.assertEqual(
            list(DeviceLot.objects.filter(lot=self.lot).values_list(
                "device_id", flat=True
            )),
            ["legacy-id"],
        )

    # --- Lot.remove -----------------------------------------------------

    def test_lot_remove_accepts_any_physical(self):
        self.lot.add("ereuse24:b2")
        self.lot.remove("ereuse24:b1")
        self.assertFalse(DeviceLot.objects.filter(lot=self.lot).exists())

    def test_lot_remove_accepts_root(self):
        self.lot.add("ereuse24:b1")
        self.lot.remove("ereuse24:b2")
        self.assertFalse(DeviceLot.objects.filter(lot=self.lot).exists())

    # --- Beneficiary.add / remove --------------------------------------

    def _make_beneficiary(self):
        shop = LotSubscription.objects.create(
            lot=self.lot,
            user=self.user,
            type=LotSubscription.Type.SHOP,
        )
        return Beneficiary.objects.create(
            lot=self.lot,
            shop=shop,
            email="beneficiary@test.local",
        )

    def test_beneficiary_add_stores_root(self):
        b = self._make_beneficiary()
        b.add("ereuse24:b3")
        self.assertEqual(
            list(DeviceBeneficiary.objects.filter(beneficiary=b).values_list(
                "device_id", flat=True
            )),
            ["ereuse24:b2"],
        )

    def test_beneficiary_add_dedupes_within_lot(self):
        b = self._make_beneficiary()
        b.add("ereuse24:b1")
        b.add("ereuse24:b3")
        b.add("ereuse24:b2")
        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary__lot=self.lot).count(),
            1,
        )

    def test_beneficiary_remove_accepts_any_physical(self):
        b = self._make_beneficiary()
        b.add("ereuse24:b2")
        b.remove("ereuse24:b1")
        self.assertFalse(
            DeviceBeneficiary.objects.filter(beneficiary=b).exists()
        )

    # --- add then alias then remove / re-add ----------------------------

    def _fresh_sp(self, value):
        SystemProperty.objects.create(
            owner=self.institution, uuid=uuid.uuid4(), value=value
        )

    def test_lot_remove_after_aliasing_deletes_stale_row(self):
        """Add before alias, then alias, then remove must succeed."""
        self._fresh_sp("ereuse24:z1")                       # signal: (z1, z1)
        self.lot.add("ereuse24:z1")                         # stored device_id=z1
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:z1",
            defaults={"root": "custom_id:Z"},
        )
        self.lot.remove("ereuse24:z1")                      # physical ref
        self.assertFalse(DeviceLot.objects.filter(lot=self.lot).exists())

    def test_lot_remove_by_new_root_after_aliasing(self):
        self._fresh_sp("ereuse24:z1")
        self.lot.add("ereuse24:z1")
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:z1",
            defaults={"root": "custom_id:Z"},
        )
        self.lot.remove("custom_id:Z")             # new canonical
        self.assertFalse(DeviceLot.objects.filter(lot=self.lot).exists())

    def test_lot_add_after_aliasing_does_not_duplicate(self):
        self._fresh_sp("ereuse24:z1")
        self.lot.add("ereuse24:z1")
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:z1",
            defaults={"root": "custom_id:Z"},
        )
        self.lot.add("ereuse24:z1")
        self.lot.add("custom_id:Z")
        self.assertEqual(
            DeviceLot.objects.filter(lot=self.lot).count(), 1
        )

    def test_beneficiary_remove_after_aliasing_deletes_stale_row(self):
        self._fresh_sp("ereuse24:w1")
        b = self._make_beneficiary()
        b.add("ereuse24:w1")                                # stored w1
        RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:w1",
            defaults={"root": "custom_id:W"},
        )
        b.remove("ereuse24:w1")
        self.assertFalse(
            DeviceBeneficiary.objects.filter(beneficiary=b).exists()
        )


class DataMigrationDedupTests(TestCase):
    """Simulate the Phase 2.1 migration on pre-existing DeviceLot/DeviceBeneficiary
    rows that still carry physical aliases.

    The migration runs on historical apps-state objects, so here we emulate
    the outcome by calling the same logic (resolve + dedup) on live rows.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="m@test.local", institution=self.institution
        )
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="m", owner=self.institution, type=self.tag
        )

        for v in ["ereuse24:p1", "ereuse24:p2", "ereuse24:p3"]:
            SystemProperty.objects.create(
                owner=self.institution, uuid=uuid.uuid4(), value=v
            )
        # p1 and p3 share canonical p2; p2 is its own root (self-ref).
        RootAlias.objects.update_or_create(
            owner=self.institution, alias="ereuse24:p1", defaults={"root": "ereuse24:p2"}
        )
        RootAlias.objects.update_or_create(
            owner=self.institution, alias="ereuse24:p3", defaults={"root": "ereuse24:p2"}
        )

    def _migrate(self):
        """Same core logic as lot/migrations/0012_canonical_device_ids.py."""
        mapping = {
            (row["owner_id"], row["alias"]): row["root"]
            for row in RootAlias.objects.values(
                "owner_id", "alias", "root"
            )
        }

        seen = set()
        for dl in DeviceLot.objects.select_related("lot").order_by("pk"):
            root = mapping.get(
                (dl.lot.owner_id, dl.device_id), dl.device_id
            )
            key = (dl.lot_id, root)
            if key in seen:
                dl.delete()
                continue
            seen.add(key)
            if root != dl.device_id:
                dl.device_id = root
                dl.save()

    def test_migration_collapses_physical_rows(self):
        # Pre-migration state: 3 DeviceLot rows, one per physical.
        DeviceLot.objects.create(lot=self.lot, device_id="ereuse24:p1")
        DeviceLot.objects.create(lot=self.lot, device_id="ereuse24:p3")
        DeviceLot.objects.create(lot=self.lot, device_id="ereuse24:p2")

        self._migrate()

        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 1)
        self.assertEqual(
            DeviceLot.objects.get(lot=self.lot).device_id, "ereuse24:p2"
        )

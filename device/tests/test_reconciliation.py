import uuid as uuidlib
from unittest.mock import patch

from django.test import TestCase

from user.models import Institution, User
from evidence.models import SystemProperty, RootAlias
from device.models import ProductCache


class _FakeDevice:
    """A Device that derives deterministic export fields from its id and the
    live SystemProperty/RootAlias state, so the projection can be exercised
    end to end without a populated Xapian.

    ``get_uuids`` mirrors the real lookup (every physical alias of the root),
    which is what makes an emptied root collapse and an aliased pair merge
    observable through the projection.
    """

    def __init__(self, id, owner):
        self.id = id
        self.owner = owner
        self.uuids = []

    def get_uuids(self):
        aliases = RootAlias.physical_aliases(self.owner, self.id)
        self.uuids = list(
            SystemProperty.objects
            .filter(owner=self.owner, value__in=aliases)
            .values_list("uuid", flat=True)
        )

    def merged_export_fields(self):
        return {
            "ID": self.id.split(":")[1][:6].upper(),
            "type": "Laptop",
            "manufacturer": "Maker-" + self.id,
            "model": "Model-" + self.id,
            "serial": "SN-" + self.id,
            "cpu_model": "CPU-" + self.id,
            "last_updated": "",
            "cpu_cores": str(len(self.uuids)),
            "ram_total": "8", "ram_type": "DDR4", "ram_slots": "2",
            "slots_used": "1", "drive": "SSD", "gpu_model": "Intel",
        }

    def storage_readings(self):
        return {}


class ReconciliationTests(TestCase):
    """The read model is maintained incrementally (the SystemProperty signal
    and RootAlias.set_alias each call rebuild/drop). It must never drift from a
    full ``rebuild_all`` recomputation: same set of roots, same field values.
    """

    def setUp(self):
        patcher = patch("device.models.Device", side_effect=_FakeDevice)
        self.addCleanup(patcher.stop)
        patcher.start()

        self.inst = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.inst)

    def _sp(self, value):
        return SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value=value)

    def _snapshot(self):
        """Comparable view of the projection: root -> stable field values
        (pk/updated excluded, as they legitimately differ between rebuilds)."""
        return {
            p.root: {
                "shortid": p.shortid, "type": p.type,
                "manufacturer": p.manufacturer, "model": p.model,
                "serial": p.serial, "cpu_model": p.cpu_model,
                "last_updated": p.last_updated, "data": p.data,
            }
            for p in ProductCache.objects.filter(owner=self.inst)
        }

    def _build_scenario(self):
        """A mix that exercises every incremental trigger: plain creates,
        a second evidence for one device, and an alias that collapses two
        physical ids onto a single canonical root."""
        self._sp("ereuse24:a1")
        self._sp("ereuse24:a2")
        self._sp("ereuse24:a3")
        self._sp("ereuse24:a3")              # second evidence, same root
        RootAlias.set_alias(self.inst, "ereuse24:a1", "ereuse24:a2")

    def test_incremental_matches_full_rebuild(self):
        self._build_scenario()
        incremental = self._snapshot()

        ProductCache.objects.filter(owner=self.inst).delete()
        ProductCache.rebuild_all(owner=self.inst)
        from_scratch = self._snapshot()

        self.assertEqual(incremental, from_scratch)

    def test_aliased_id_leaves_no_stale_row(self):
        self._build_scenario()
        roots = set(self._snapshot())
        # a1 was aliased onto a2; only a2 and a3 remain canonical.
        self.assertEqual(roots, {"ereuse24:a2", "ereuse24:a3"})

    def test_merged_root_reflects_both_physical_evidences(self):
        self._build_scenario()
        a2 = ProductCache.objects.get(owner=self.inst, root="ereuse24:a2")
        # a1 + a2 evidences now resolve to the a2 root.
        self.assertEqual(a2.data["cpu_cores"], "2")

    def test_rebuild_all_scoped_to_owner_leaves_other_untouched(self):
        """rebuild_all(owner=A) must only rebuild A's roots; B's rows are not
        even re-saved (their auto_now ``updated`` stays put)."""
        other = Institution.objects.create(name="Other")
        SystemProperty.objects.create(
            owner=other, uuid=uuidlib.uuid4(), value="ereuse24:zz")
        self._sp("ereuse24:a1")
        before = ProductCache.objects.get(owner=other, root="ereuse24:zz")

        seen_owners = []
        with patch.object(
            ProductCache, "rebuild",
            side_effect=lambda owner, root: seen_owners.append(owner),
        ):
            ProductCache.rebuild_all(owner=self.inst)

        self.assertTrue(seen_owners)
        self.assertTrue(all(o == self.inst for o in seen_owners))
        after = ProductCache.objects.get(owner=other, root="ereuse24:zz")
        self.assertEqual(before.pk, after.pk)
        self.assertEqual(before.updated, after.updated)

    def test_rebuild_all_is_idempotent(self):
        self._build_scenario()
        ProductCache.rebuild_all(owner=self.inst)
        once = self._snapshot()
        ProductCache.rebuild_all(owner=self.inst)
        twice = self._snapshot()
        self.assertEqual(once, twice)

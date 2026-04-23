"""Phase 3 tests — UserProperty.device_id anchored to canonical root.

Covers:
- Basic creation with device_id populated from RootAlias.
- Read path: Device.get_user_properties() finds properties via device_id.
- Shared properties across physical aliases of the same canonical device.
- _sync_memberships migrates UserProperty on set_alias.
- Deduplication on key collision after alias merge.
- Unique constraint enforcement.
- ERASE_SERVER regression: uuid-based flow unchanged.
- Data migration helper: same logic as 0010 RunPython.
"""
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from device.models import Device
from evidence.models import RootAlias, SystemProperty, UserProperty
from user.models import Institution


def _sp(institution, value, sp_uuid=None):
    """Create a SystemProperty and its auto-generated RootAlias self-reference."""
    return SystemProperty.objects.create(
        owner=institution,
        uuid=sp_uuid or uuid.uuid4(),
        value=value,
    )


def _up(institution, device_id, key, value="v"):
    """Create a UserProperty(type=USER) anchored to device_id."""
    return UserProperty.objects.create(
        owner=institution,
        device_id=device_id,
        key=key,
        value=value,
        type=UserProperty.Type.USER,
    )


class UserPropertyDeviceIdBasicTests(TestCase):
    """Basic creation and read-path tests."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst A")

    def test_create_user_property_with_device_id(self):
        _sp(self.inst, "ereuse24:ABC")
        up = _up(self.inst, "ereuse24:ABC", "color", "blue")
        self.assertEqual(up.device_id, "ereuse24:ABC")
        self.assertIsNone(up.uuid)

    def test_get_user_properties_returns_by_device_id(self):
        _sp(self.inst, "ereuse24:ABC")
        _up(self.inst, "ereuse24:ABC", "color", "blue")
        device = Device(id="ereuse24:ABC", owner=self.inst)
        props = list(device.get_user_properties())
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].key, "color")

    def test_get_user_properties_empty_without_owner(self):
        device = Device.__new__(Device)
        device.id = "ereuse24:ABC"
        device.owner = None
        device._canonical_cache = None
        result = device.get_user_properties()
        self.assertEqual(result.count(), 0)

    def test_get_user_properties_ignores_other_institution(self):
        other = Institution.objects.create(name="Inst B")
        _sp(self.inst, "ereuse24:ABC")
        _sp(other, "ereuse24:ABC")
        _up(other, "ereuse24:ABC", "color", "red")
        device = Device(id="ereuse24:ABC", owner=self.inst)
        self.assertEqual(device.get_user_properties().count(), 0)


class UserPropertySharedAcrossAliasesTests(TestCase):
    """Two physical IDs aliased to the same root share UserProperties."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst Shared")
        _sp(self.inst, "ereuse24:X")
        _sp(self.inst, "ereuse26:Y")
        RootAlias.set_alias(self.inst, "ereuse24:X", "ereuse26:Y")

    def test_property_created_on_root_visible_from_alias(self):
        canonical = RootAlias.resolve_root(self.inst, "ereuse24:X")
        _up(self.inst, canonical, "tag", "shared")

        device_from_alias = Device(id="ereuse24:X", owner=self.inst)
        props = list(device_from_alias.get_user_properties())
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].key, "tag")

    def test_property_created_on_alias_visible_from_root(self):
        # create on the non-canonical physical, but resolve first
        canonical = RootAlias.resolve_root(self.inst, "ereuse24:X")
        _up(self.inst, canonical, "tag", "shared")

        device_from_root = Device(id="ereuse26:Y", owner=self.inst)
        props = list(device_from_root.get_user_properties())
        self.assertEqual(len(props), 1)


class UserPropertySyncMembershipsTests(TestCase):
    """_sync_memberships migrates UserProperty on alias change."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst Sync")
        _sp(self.inst, "ereuse24:A")
        _sp(self.inst, "ereuse24:B")

    def test_property_migrated_to_new_root_after_set_alias(self):
        # Property created before aliasing, anchored to A (self-referential root).
        _up(self.inst, "ereuse24:A", "status", "ok")
        RootAlias.set_alias(self.inst, "ereuse24:A", "ereuse24:B")

        up = UserProperty.objects.get(owner=self.inst, key="status")
        self.assertEqual(up.device_id, "ereuse24:B")

    def test_key_collision_on_merge_keeps_most_recent(self):
        # Both devices have the same key; after aliasing only one should survive.
        now = timezone.now()
        up_old = UserProperty.objects.create(
            owner=self.inst, device_id="ereuse24:A", key="color",
            value="red", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_old.pk).update(created=now)
        later = now + timedelta(milliseconds=1)
        up_new = UserProperty.objects.create(
            owner=self.inst, device_id="ereuse24:B", key="color",
            value="blue", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_new.pk).update(created=later)
        RootAlias.set_alias(self.inst, "ereuse24:A", "ereuse24:B")

        surviving = UserProperty.objects.filter(
            owner=self.inst, key="color", type=UserProperty.Type.USER
        )
        self.assertEqual(surviving.count(), 1)
        self.assertEqual(surviving.first().value, "blue")

    def test_key_collision_winner_not_on_new_root(self):
        # Regression: device A (new_root) has key a1 (older).
        # Device B (alias) also has key a1 (newer, so it is the winner).
        # set_alias(B -> A) must not raise UNIQUE constraint violation when
        # updating winner B's device_id to A while A's row still exists.
        now = timezone.now()
        up_old = UserProperty.objects.create(
            owner=self.inst, device_id="ereuse24:A", key="a1",
            value="old", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_old.pk).update(created=now)
        later = now + timedelta(milliseconds=1)
        up_new = UserProperty.objects.create(
            owner=self.inst, device_id="ereuse24:B", key="a1",
            value="new", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_new.pk).update(created=later)
        # A is the new_root; B is the alias being pointed at A
        RootAlias.set_alias(self.inst, "ereuse24:B", "ereuse24:A")

        surviving = UserProperty.objects.filter(
            owner=self.inst, key="a1", type=UserProperty.Type.USER
        )
        self.assertEqual(surviving.count(), 1)
        self.assertEqual(surviving.first().value, "new")
        self.assertEqual(surviving.first().device_id, "ereuse24:A")

    def test_different_keys_both_survive_merge(self):
        _up(self.inst, "ereuse24:A", "key-a", "v1")
        _up(self.inst, "ereuse24:B", "key-b", "v2")
        RootAlias.set_alias(self.inst, "ereuse24:A", "ereuse24:B")

        props = UserProperty.objects.filter(
            owner=self.inst, device_id="ereuse24:B",
            type=UserProperty.Type.USER,
        )
        self.assertEqual(props.count(), 2)


class UserPropertyUniqueConstraintTests(TestCase):
    """Unique constraint (key, device_id, owner) for type=USER."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst UC")
        _sp(self.inst, "ereuse24:Z")

    def test_duplicate_key_device_owner_raises(self):
        _up(self.inst, "ereuse24:Z", "dup-key")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _up(self.inst, "ereuse24:Z", "dup-key")

    def test_same_key_different_device_allowed(self):
        _sp(self.inst, "ereuse24:W")
        _up(self.inst, "ereuse24:Z", "color")
        _up(self.inst, "ereuse24:W", "color")
        self.assertEqual(
            UserProperty.objects.filter(
                owner=self.inst, key="color",
                type=UserProperty.Type.USER,
            ).count(),
            2,
        )

    def test_same_key_different_institution_allowed(self):
        other = Institution.objects.create(name="Inst Other")
        _sp(other, "ereuse24:Z")
        _up(self.inst, "ereuse24:Z", "color")
        _up(other, "ereuse24:Z", "color")
        self.assertEqual(
            UserProperty.objects.filter(key="color", type=UserProperty.Type.USER).count(),
            2,
        )


class EraseServerRegressionTests(TestCase):
    """ERASE_SERVER flow must remain completely unchanged."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst ES")
        self.sp_uuid = uuid.uuid4()
        _sp(self.inst, "ereuse24:ES", sp_uuid=self.sp_uuid)

    def test_erase_server_created_with_uuid_no_device_id(self):
        up = UserProperty.objects.create(
            owner=self.inst,
            uuid=self.sp_uuid,
            key="ERASE_SERVER",
            value="true",
            type=UserProperty.Type.ERASE_SERVER,
        )
        self.assertEqual(up.uuid, self.sp_uuid)
        self.assertIsNone(up.device_id)

    def test_erase_server_unique_constraint_by_key_uuid(self):
        UserProperty.objects.create(
            owner=self.inst, uuid=self.sp_uuid,
            key="ERASE_SERVER", value="true",
            type=UserProperty.Type.ERASE_SERVER,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserProperty.objects.create(
                    owner=self.inst, uuid=self.sp_uuid,
                    key="ERASE_SERVER", value="false",
                    type=UserProperty.Type.ERASE_SERVER,
                )

    def test_erase_server_not_returned_by_get_user_properties(self):
        UserProperty.objects.create(
            owner=self.inst, uuid=self.sp_uuid,
            key="ERASE_SERVER", value="true",
            type=UserProperty.Type.ERASE_SERVER,
        )
        device = Device(id="ereuse24:ES", owner=self.inst)
        self.assertEqual(device.get_user_properties().count(), 0)


class DataMigrationLogicTests(TestCase):
    """Verify that the populate_device_id migration logic works correctly.

    We replicate the migration function logic directly on live models
    (no need to roll back/forward the actual migration in tests).
    """

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst Mig")

    def test_uuid_resolves_to_canonical_root(self):
        sp_uuid = uuid.uuid4()
        _sp(self.inst, "ereuse24:MIG", sp_uuid=sp_uuid)
        # Simulate a legacy UserProperty row with only uuid set (pre-migration state).
        up = UserProperty.objects.create(
            owner=self.inst,
            uuid=sp_uuid,
            key="legacy-key",
            value="v",
            type=UserProperty.Type.USER,
        )
        # Run the resolution logic.
        sp = SystemProperty.objects.filter(uuid=sp_uuid).first()
        root = RootAlias.resolve_root(self.inst, sp.value)
        UserProperty.objects.filter(pk=up.pk).update(device_id=root)

        up.refresh_from_db()
        self.assertEqual(up.device_id, "ereuse24:MIG")

    def test_uuid_resolves_through_alias(self):
        sp_uuid = uuid.uuid4()
        _sp(self.inst, "ereuse24:PHYS", sp_uuid=sp_uuid)
        RootAlias.set_alias(self.inst, "ereuse24:PHYS", "custom_id:CANON")

        sp = SystemProperty.objects.filter(uuid=sp_uuid).first()
        root = RootAlias.resolve_root(self.inst, sp.value)
        self.assertEqual(root, "custom_id:CANON")

    def test_duplicate_device_id_after_migration_deduplicated(self):
        sp1 = uuid.uuid4()
        sp2 = uuid.uuid4()
        _sp(self.inst, "ereuse24:D1", sp_uuid=sp1)
        _sp(self.inst, "ereuse24:D2", sp_uuid=sp2)

        now = timezone.now()
        up_old = UserProperty.objects.create(
            owner=self.inst, uuid=sp1, key="k", value="old",
            device_id="ereuse24:D1", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_old.pk).update(created=now)
        later = now + timedelta(milliseconds=1)
        up_new = UserProperty.objects.create(
            owner=self.inst, uuid=sp2, key="k", value="new",
            device_id="ereuse24:D2", type=UserProperty.Type.USER,
        )
        UserProperty.objects.filter(pk=up_new.pk).update(created=later)

        # Simulate migration deduplication: both resolve to "ereuse24:D2".
        # newest-first: up_new wins, up_old is deleted.
        canonical = "ereuse24:D2"
        rows = list(
            UserProperty.objects.filter(
                owner=self.inst, key="k", type=UserProperty.Type.USER,
            ).order_by("-created", "-pk")
        )
        seen = set()
        for row in rows:
            target = canonical  # both would resolve here
            if row.key in seen:
                row.delete()
                continue
            seen.add(row.key)
            if row.device_id != target:
                UserProperty.objects.filter(pk=row.pk).update(device_id=target)

        remaining = UserProperty.objects.filter(
            owner=self.inst, device_id=canonical, key="k",
            type=UserProperty.Type.USER,
        )
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().value, "new")

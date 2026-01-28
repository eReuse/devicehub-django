import json
import hashlib
import re

from dmidecode import DMIParse
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings

import json

from django.db.models import Q
from utils.constants import STR_EXTEND_SIZE, CHASSIS_DH
from evidence.xapian import search
from evidence.parse_details import ParseSnapshot
from evidence.normal_parse_details import get_inxi, get_inxi_key

from device.product_cache import ProductCache



class Property(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey('user.Institution', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        #Only for shared behaviour, it is not a table
        abstract = True


class SystemProperty(Property):
    uuid = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "uuid"], name="system_unique_type_key_uuid"),
            models.CheckConstraint(
                check=Q(value__contains=":"),
                name="systemproperty_value_has_algorithm_prefix"),
        ]

    @property
    def shortid(self):
        return self.value.split(":")[1][:6].upper()

    @property
    def hid(self):
        return self.value.split(":")[1]


class CredentialProperty(Property):
    credential = models.JSONField()
    uuid = models.UUIDField(null=True, blank=True)
    description = models.CharField(
        "Description",
        max_length=255,
        null=True,
        blank=True,
        help_text="E.g. 'Digital Facility Record' or 'Product Passport'"
    )


class UserProperty(Property):

    class Type(models.IntegerChoices):
        USER = 1, "User"
        ERASE_SERVER = 2, "EraseServer"

    uuid = models.UUIDField(null=True, blank=True)
    device_id = models.CharField(max_length=STR_EXTEND_SIZE, null=True, blank=True)
    type = models.SmallIntegerField(choices=Type, default=Type.USER)

    class Meta:
        constraints = [
            # USER properties are keyed by (key, device_id, owner); uuid is unused.
            models.UniqueConstraint(
                fields=["key", "device_id", "owner"],
                condition=Q(type=1),
                name="userproperty_unique_user_key_device_owner",
            ),
            # ERASE_SERVER properties keep the original (key, uuid) uniqueness.
            models.UniqueConstraint(
                fields=["key", "uuid"],
                condition=Q(type=2),
                name="userproperty_unique_eraseserver_key_uuid",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "device_id"], name="userproperty_owner_device_idx"),
        ]


class RootAlias(models.Model):
    """All SystemProperty.value have one RootAlias.alias and no more than one
       RootAlias.root is editable but RootAlias.alias is not possible
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField()
    owner = models.ForeignKey('user.Institution', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    alias = models.CharField(max_length=STR_EXTEND_SIZE)
    root = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "alias"], name="rootalias_unique"),
            models.CheckConstraint(
                check=Q(alias__contains=":") & Q(root__contains=":"),
                name="rootalias_ids_have_algorithm_prefix"),
        ]
        indexes = [
            models.Index(fields=["owner", "updated"], name="evidence_ro_owner_upd_idx"),
        ]

    @property
    def root_hid(self):
        return self.root.split(":")[1]

    @classmethod
    def resolve_root(cls, owner, v):
        """Resolve ``v`` to its canonical root for ``owner``.

        Every SystemProperty.value has a RootAlias row with
        ``alias=value``; the ``root`` is the canonical id (self-reference
        for devices with no custom alias, or the user/custom alias
        otherwise). Falls back to ``v`` itself when no row exists (legacy
        data or ids not owned by this institution) so callers are safe to
        pass arbitrary strings.
        """
        row = cls.objects.filter(owner=owner, alias=v).values("root").first()
        return row["root"] if row else v

    @classmethod
    def physical_aliases(cls, owner, v):
        """All ids known to belong to the same canonical device as ``v``.

        Suitable for ``device_id__in=...`` filters against tables that
        store a device identity as a plain CharField (DeviceLot,
        DeviceBeneficiary). It covers rows stored with a previous value
        of the canonical root (e.g. inserted before the user aliased the
        device, or left over from a later re-aliasing): every sibling
        alias sharing the resolved root is included, plus ``v`` and the
        root itself as defensive fallbacks.
        """
        root = cls.resolve_root(owner, v)
        aliases = set(
            cls.objects.filter(owner=owner, root=root)
            .values_list("alias", flat=True)
        )
        aliases.add(root)
        aliases.add(v)
        return list(aliases)

    # -- depth-1 invariant helpers -------------------------------------

    @classmethod
    def is_terminal_root(cls, owner, new_root):
        """True if pointing an alias to ``new_root`` does not create a chain.

        A target is terminal when either:
        - no ``RootAlias`` row exists with ``alias=new_root`` (fresh
          custom_id not backed by a SystemProperty), or
        - the existing row is self-referential (``alias == root``).

        If instead the target has ``alias != root``, ``new_root`` is itself
        aliased to something else and using it as a root would create a
        two-hop chain ``A -> new_root -> X``.
        """
        target = cls.objects.filter(owner=owner, alias=new_root).first()
        return target is None or target.root == target.alias

    @classmethod
    def has_dependents(cls, owner, alias):
        """True if other aliases already use ``alias`` as their root.

        Re-pointing ``alias`` when it is someone else's root would leave
        those dependents with a stale root (they'd point at a value that
        is itself now aliased elsewhere).
        """
        return (
            cls.objects.filter(owner=owner, root=alias)
            .exclude(alias=alias)
            .exists()
        )

    @classmethod
    def set_alias(cls, owner, alias, new_root, user=None):
        """Write ``alias -> new_root`` enforcing the depth-1 invariant.

        Raises ``ValueError`` if the target is not terminal or the source
        already has external dependents. When ``new_root == alias`` the
        call is a self-reset (the "empty" state of an alias) and both
        checks are skipped since a self-reference never creates a chain
        nor orphans dependents. After the edge is stored,
        DeviceLot/DeviceBeneficiary rows are collapsed/migrated so the
        canonical invariant holds (same logic as migration 0012).
        """
        existing = cls.objects.filter(owner=owner, alias=alias).first()
        old_root = existing.root if existing else None

        if new_root != alias:
            if not cls.is_terminal_root(owner, new_root):
                raise ValueError(
                    f"target {new_root!r} is not a terminal root"
                )
            if cls.has_dependents(owner, alias):
                raise ValueError(
                    f"{alias!r} cannot be re-rooted: other aliases depend on it"
                )

        if existing:
            if existing.root != new_root or existing.user != user:
                cls.objects.filter(pk=existing.pk).update(
                    root=new_root, user=user,
                )
            obj = cls.objects.get(pk=existing.pk)
        else:
            now = timezone.now()
            obj = cls.objects.create(
                owner=owner, alias=alias, root=new_root, user=user,
                created=now, updated=now,
            )

        if old_root != new_root:
            cls._sync_memberships(owner, alias, new_root, old_root=old_root)
            # The read model follows the canonical change: rebuild the gaining
            # root; rebuild the losing root if it still has aliases, else drop
            # it (``alias`` was its last child, mirroring _sync_memberships).
            ProductCache.rebuild(owner, new_root)
            if old_root is not None:
                old_still_canonical = cls.objects.filter(
                    owner=owner, root=old_root
                ).exists()
                if old_still_canonical:
                    ProductCache.rebuild(owner, old_root)
                else:
                    ProductCache.drop(owner, old_root)
        return obj

    @classmethod
    def _sync_memberships(cls, owner, alias, new_root, old_root=None):
        """Keep DeviceLot/DeviceBeneficiary canonical after an edge change.

        Any row whose ``device_id`` is one of the new canonical family's
        physical aliases is rewritten to ``new_root`` and deduplicated
        (one per lot for DeviceLot, one per beneficiary for
        DeviceBeneficiary).

        If ``old_root`` is no longer a canonical root of anyone after the
        change (i.e. ``alias`` was its last child), its lot/beneficiary
        rows would be orphaned; migrate them to ``new_root`` so the
        device keeps its membership under its new identity.
        """
        # Lazy imports to avoid a circular dependency at module load time
        # (lot.models imports from evidence.models).
        from lot.models import DeviceLot, DeviceBeneficiary

        physicals = set(cls.physical_aliases(owner, alias))

        if old_root and old_root != new_root:
            old_still_canonical = cls.objects.filter(
                owner=owner, root=old_root
            ).exists()
            if not old_still_canonical:
                physicals.add(old_root)

        physicals = list(physicals)

        seen = set()
        for dl in (
            DeviceLot.objects
            .filter(lot__owner=owner, device_id__in=physicals)
            .order_by("pk")
        ):
            key = (dl.lot_id, new_root)
            if key in seen:
                dl.delete()
                continue
            seen.add(key)
            if dl.device_id != new_root:
                DeviceLot.objects.filter(pk=dl.pk).update(
                    device_id=new_root
                )

        seen = set()
        for db in (
            DeviceBeneficiary.objects
            .filter(
                beneficiary__lot__owner=owner,
                device_id__in=physicals,
            )
            .order_by("pk")
        ):
            key = (db.beneficiary_id, new_root)
            if key in seen:
                db.delete()
                continue
            seen.add(key)
            if db.device_id != new_root:
                DeviceBeneficiary.objects.filter(pk=db.pk).update(
                    device_id=new_root
                )

        # Migrate UserProperty(type=USER) to the new canonical root.
        # Two-phase to avoid UNIQUE(key, device_id, owner_id) violations:
        # 1. Identify the winning pk per key (newest row wins).
        # 2. Delete all non-winners first, then bulk-update survivors to new_root.
        #    Deleting before updating ensures no collision when two devices share
        #    the same key and one of them already has device_id=new_root.
        winner_pks = {}  # key -> pk of newest row
        for up in (
            UserProperty.objects
            .filter(owner=owner, device_id__in=physicals, type=UserProperty.Type.USER)
            .order_by("-created", "-pk")
            .values("pk", "key")
        ):
            if up["key"] not in winner_pks:
                winner_pks[up["key"]] = up["pk"]

        # Phase 1: delete duplicates
        UserProperty.objects.filter(
            owner=owner, device_id__in=physicals, type=UserProperty.Type.USER,
        ).exclude(pk__in=winner_pks.values()).delete()

        # Phase 2: point all survivors at the canonical root
        UserProperty.objects.filter(
            pk__in=winner_pks.values(),
        ).exclude(device_id=new_root).update(device_id=new_root)


@receiver(post_save, sender=SystemProperty)
def ensure_root_alias_self_reference(sender, instance, created, **kwargs):
    """Keep RootAlias as the canonical catalog of devices.

    Whenever a SystemProperty is created, guarantee there is a self-referential
    RootAlias row (alias=value, root=value) for the same owner. This makes
    ``SELECT DISTINCT root FROM RootAlias`` a complete listing of every device
    known to the institution, and ``RootAlias.get(alias=X)`` a total function.
    """
    if not created:
        return
    existing = RootAlias.objects.filter(
        owner=instance.owner, alias=instance.value,
    ).first()
    if existing is None:
        RootAlias.objects.create(
            owner=instance.owner,
            alias=instance.value,
            root=instance.value,
            user=instance.user,
            created=instance.created,
            updated=instance.created,
        )
    elif instance.created > existing.updated:
        RootAlias.objects.filter(pk=existing.pk).update(
            updated=instance.created,
        )

    # A new evidence changes the device's latest state: refresh its read model.
    root = RootAlias.resolve_root(instance.owner, instance.value)
    ProductCache.rebuild(instance.owner, root)


class Evidence:
    def __init__(self, uuid):
        self.uuid = uuid
        self.uploaded_by = None
        self.owner = None
        self.doc = None
        self.created = None
        self.dmi = None
        self.inxi = None
        self.properties = []
        self.components = []
        self.default = "n/a"

        self.get_owner()
        self.get_time()

    def get_properties(self):
        self.properties = SystemProperty.objects.filter(
            uuid=self.uuid
        ).order_by("created")

    def get_credential(self):
        self.credentials = CredentialProperty.objects.filter(
            uuid=self.uuid
        ).order_by("-created")
        return self.credentials.first()

    def get_owner(self):
        if not self.properties:
            self.get_properties()
        a = self.properties.first()
        if a:
            self.owner = a.owner
            self.uploaded_by = a.user

    def get_phid(self):
        if not self.doc:
            self.get_doc()

        return hashlib.sha3_256(json.dumps(self.doc)).hexdigest()

    def get_doc(self):
        self.doc = {}
        self.inxi = None

        if not self.owner:
            self.get_owner()

        qry = 'uuid:"{}"'.format(self.uuid)
        matches = search(self.owner, qry, limit=1)
        if matches and matches.size() < 0:
            return

        for xa in matches:
            self.doc = json.loads(xa.document.get_data())

        if self.is_beta():
            parse = ParseSnapshot(self.doc)
            device = parse.device
            if not device:
                return
            self.device_manufacturer = device.get("manufacturer") or ''
            self.device_model = device.get("model") or ''
            self.device_serial_number = device.get("serialNumber") or ''
            self.device_chassis = device.get("chassis") or ''
            self.device_version = device.get("version") or ''
            self.components = parse.components

        if self.is_legacy():
            return

        if self.doc.get("credentialSubject"):
            for ev in self.doc["evidence"]:
                if "dmidecode" == ev.get("operation"):
                    dmidecode_raw = ev["output"]
                    if dmidecode_raw:
                        self.dmi = DMIParse(dmidecode_raw)
                if "inxi" == ev.get("operation"):
                    self.inxi = ev["output"]
                    if isinstance(ev["output"], str):
                        self.inxi = json.loads(ev["output"])
        else:
            dmidecode_raw = self.doc["data"]["dmidecode"]
            inxi_raw = self.doc.get("data", {}).get("inxi")
            self.dmi = DMIParse(dmidecode_raw)
            try:
                self.inxi = json.loads(inxi_raw)
            except Exception:
                pass
        if self.inxi:
            try:
                if isinstance(self.inxi, str):
                    self.inxi = json.loads(self.inxi)
                machine = get_inxi_key(self.inxi, 'Machine')
                for m in machine:
                    system = get_inxi(m, "System")
                    if system:
                        self.device_manufacturer = system
                        self.device_model = get_inxi(m, "product")
                        self.device_serial_number = get_inxi(m, "serial")
                        self.device_version = get_inxi(m, "v")
                    else:
                        self.device_manufacturer = getattr(self, 'device_manufacturer', '') or get_inxi(m, "Mobo")
                        self.device_model = getattr(self, 'device_model', '') or get_inxi(m, "model")
                        self.device_serial_number = getattr(self, 'device_serial_number', '') or get_inxi(m, "serial")
                    self.device_chassis = getattr(self, 'device_chassis', '') or get_inxi(m, "Type")
            except Exception:
                return

    def get_time(self):
        if not self.doc:
            self.get_doc()
        self.created = self.doc.get("endTime")
        if not self.created:
            self.created = self.get_time_created()

    def get_time_created(self):
        return self.properties.last().created.isoformat()

    def get_components(self):
        if self.is_beta():
            return self.components

        self.set_components()
        return self.components

    def get_manufacturer(self):
        if self.is_web_snapshot():
            kv = self.doc.get('kv', {})
            if len(kv) < 1:
                return ""
            return list(self.doc.get('kv').values())[0]

        if self.inxi or self.is_beta():
            return getattr(self, 'device_manufacturer', '')

        if self.is_legacy():
            return self.doc.get('device', {}).get('manufacturer', '')

        try:
            return self.dmi.manufacturer().strip()
        except Exception:
            return ''

    def get_model(self):
        if self.is_web_snapshot():
            kv = self.doc.get('kv', {})
            if len(kv) < 2:
                return ""
            return list(self.doc.get('kv').values())[1]

        if self.inxi or self.is_beta():
            return getattr(self, 'device_model', '')

        if self.is_legacy():
            model = self.doc.get('device', {}).get('model', '') or ''
            version = self.doc.get('device', {}).get('version', '') or ''
            return "{} {}".format(model, version)

        try:
            return self.dmi.model().strip()
        except Exception:
            return ''

    def get_chassis(self):
        if self.inxi or self.is_beta():
            return getattr(self, 'device_chassis', '')

        if self.is_legacy():
            chassis = self.doc.get('device', {}).get('chassis', '')
            for k, v in CHASSIS_DH.items():
                if chassis.lower() in v:
                    return k
            return chassis

        dmi_chassis = self.dmi.get("Chassis")
        if not dmi_chassis:
            return ""

        chassis = dmi_chassis[0].get("Type", '_virtual')
        lower_type = chassis.lower()

        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return ""

    def get_serial_number(self):
        if self.inxi or self.is_beta():
            return getattr(self, 'device_serial_number', '')

        if self.is_legacy():
            return self.doc.get('device', {}).get('serialNumber', '')

        try:
            return self.dmi.serial_number().strip()
        except Exception:
            return ''

    def get_version(self):
        if self.inxi or self.is_beta():
            return getattr(self, 'device_version', '')

        return ""

    # Component-derived export fields. Each getter handles the per-format
    # shape differences (like get_manufacturer does), reading from a parsed,
    # memoized component list. An evidence whose components cannot be parsed
    # (e.g. credentialSubject, not yet supported) yields an empty list, so the
    # getters return "" and the projection merge backfills from another
    # evidence instead of crashing.
    STORAGE_TYPES = ("Storage", "SolidStateDrive", "HardDrive")
    NO_MODULE = "no module installed"

    def export_components(self):
        if getattr(self, "_export_components_memo", None) is None:
            try:
                self._export_components_memo = self.get_components()
            except Exception:
                self._export_components_memo = []
        return self._export_components_memo

    def get_cpu_model(self):
        model = ""
        for c in self.export_components():
            if c.get("type") == "Processor":
                model = c.get("model", "") or ""
        return model

    def get_cpu_cores(self):
        cores = ""
        for c in self.export_components():
            if c.get("type") == "Processor":
                cores = c.get("cores", "")
        return cores

    def get_ram_total(self):
        # Sum the size of every populated RamModule instead of relying on the
        # motherboard's installedRam, which inxi frequently leaves empty.
        total = 0.0
        found = False
        for c in self.export_components():
            if c.get("type") != "RamModule":
                continue
            gib = self._ram_size_to_gib(c.get("size", ""))
            if gib:
                total += gib
                found = True
        if not found:
            return ""
        return int(total) if total == int(total) else round(total, 1)

    @staticmethod
    def _ram_size_to_gib(size):
        # RamModule sizes come from inxi as strings like "4 GB", "2048 MiB" or
        # "8 GiB". Normalise to GiB; treat GB/GiB as equivalent.
        if not size:
            return 0.0
        match = re.match(r"\s*([\d.]+)\s*([a-zA-Z]+)?", str(size))
        if not match:
            return 0.0
        try:
            value = float(match.group(1))
        except ValueError:
            return 0.0
        unit = (match.group(2) or "gb").lower()
        if unit in ("mib", "mb"):
            value /= 1024
        elif unit in ("kib", "kb"):
            value /= 1024 * 1024
        elif unit in ("tib", "tb"):
            value *= 1024
        return value

    def get_ram_type(self):
        ram_type = ""
        for c in self.export_components():
            if c.get("type") == "RamModule":
                ram_type = c.get("interface", "")
                if ram_type != self.NO_MODULE:
                    break
        return ram_type

    def get_ram_slots(self):
        rams = [c for c in self.export_components()
                if c.get("type") == "RamModule"]
        return len(rams) if rams else ""

    def get_ram_slots_used(self):
        rams = [c for c in self.export_components()
                if c.get("type") == "RamModule"]
        if not rams:
            return ""
        return sum(1 for c in rams
                   if c.get("interface", "") != self.NO_MODULE)

    def get_drive(self):
        drives = []
        for c in self.export_components():
            if c.get("type") in self.STORAGE_TYPES:
                size = c.get("size", "")
                if size:
                    drives.append(" {} {} ({} )".format(
                        c.get("interface", ""), c.get("model", ""), size))
        return ", ".join(drives)

    def get_gpu_model(self):
        models = []
        for c in self.export_components():
            if c.get("type") == "GraphicCard":
                model = c.get("model", "")
                if model:
                    models.append(model)
        return ", ".join(models)

    def get_alias(self):
        aliases = [ x.value for x in self.properties ]
        alias_obj = RootAlias.objects.filter(
            alias__in = aliases,
        ).order_by("-updated")

        if alias_obj:
            return alias_obj[0].root
        else:
            return self.properties[0].value

    @classmethod
    def get_all(cls, user):
        return SystemProperty.objects.filter(
            owner=user.institution,
        ).order_by("-created").distinct()

    @classmethod
    def get_user_evidences(cls, user):
        return SystemProperty.objects.filter(
            owner=user.institution,
            user=user
        ).order_by("-created").distinct()

    @classmethod
    def get_device_evidences(cls, user, uuids):
        return SystemProperty.objects.filter(
            owner=user.institution,
            uuid__in=uuids
        ).order_by("-created").distinct()

    def set_components(self):
        self.components = ParseSnapshot(self.doc).components

    def is_beta(self):
        return self.doc.get("version") == '2022.12.2-beta'

    def is_legacy(self):
        if self.doc.get("credentialSubject"):
            return False

        return self.doc.get("software") != "workbench-script"

    def is_web_snapshot(self):
        return self.doc.get("type") == "WebSnapshot"

    def is_photo_evidence(self):
        return self.doc.get("type") == "photo25"

    def did_document(self):
        if not self.doc.get("credentialSubject"):
            return ''
        did = self.doc.get('issuer').get('id')
        if "did:web" not in did:
            return ''

        return  "https://{}/did.json".format(
            did.split("did:web:")[1].replace(":", "/")
        )

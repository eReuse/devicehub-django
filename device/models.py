from django.db import models
from django.db.models import Max
from django.urls import reverse
from django.db.models import Subquery, F, Window, Max
from django.db.models.functions import RowNumber
from django.utils.translation import gettext_lazy as _

from utils.constants import ALGOS
from evidence.models import CredentialProperty, SystemProperty, UserProperty, Evidence, RootAlias
from django.utils.dateparse import parse_datetime
from lot.models import DeviceLot, DeviceBeneficiary
from action.models import State
from user.models import InstitutionLabelSettings, LabelVersion, QRContentType

from django.utils.translation import gettext_lazy as _

class Device:
    class Types(models.TextChoices):
        DESKTOP = "Desktop"
        LAPTOP = "Laptop"
        SERVER = "Server"
        GRAPHICCARD = "GraphicCard"
        HARDDRIVE = "HardDrive"
        SOLIDSTATEDRIVE = "SolidStateDrive"
        MOTHERBOARD = "Motherboard"
        NETWORKADAPTER = "NetworkAdapter"
        PROCESSOR = "Processor"
        RAMMODULE = "RamModule"
        SOUNDCARD = "SoundCard"
        DISPLAY = "Display"
        BATTERY = "Battery"
        CAMERA = "Camera"
        SWITCH = "Switch"
        ROUTER = "Router"
        ROUTERWIFI = "RouterWifi"

        # --- Raw Materials (Dismantling Outputs) ---
        PLASTIC = "Plastic"
        ALUMINIUM = "Aluminium"
        COPPER = "Copper"
        STEEL = "Steel"
        GLASS = "Glass"
        GOLD = "Gold"
        LITHIUM = "Lithium"
        PCB = "PCB"
        MIXED_EWASTE = "MixedEwaste"

    def __init__(self, *args, **kwargs):
        # the id is the chid of the device
        # in the rootalias table id is the root
        self.id = kwargs["id"]
        self.uuid = kwargs.get("uuid")
        self.lot = kwargs.get("lot")
        self.pk = self.id
        self.hid = self.id.split(":")[1]
        self.algorithm = None
        self.owner = kwargs.get("owner")
        self.properties = []
        self.hids = []
        self.uuids = []
        self.evidences = []
        self.lots = []
        self.last_evidence = None
        self._canonical_cache = None
        self._physicals_cache = None
        self.get_shortid()
        self.get_last_evidence()

    def _canonical_id(self):
        if self._canonical_cache is not None:
            return self._canonical_cache
        self._canonical_cache = self.get_canonical_id_for(self.id, self.owner)
        return self._canonical_cache

    def _physical_ids(self):
        """All physical IDs that share the same canonical device."""
        if self._physicals_cache is not None:
            return self._physicals_cache
        if not self.owner:
            self._physicals_cache = [self.id]
            return self._physicals_cache

        canonical = self._canonical_id()
        ids = list(
            RootAlias.objects.filter(owner=self.owner, root=canonical)
            .values_list("alias", flat=True)
        )
        self._physicals_cache = ids or [self.id]
        return self._physicals_cache

    @classmethod
    def get_canonical_id_for(cls, id, owner=None):
        """Canonical id without instantiating a full Device.

        Thanks to invariant (every SystemProperty.value has a
        RootAlias row with alias=value), any physical ID resolves through one
        lookup; a custom_id or unknown ID falls back to itself.
        """
        if not owner:
            return id
        alias = RootAlias.objects.filter(owner=owner, alias=id).first()
        return alias.root if alias else id

    @classmethod
    def get_shortid_for(cls, id, owner=None):
        canonical = cls.get_canonical_id_for(id, owner)
        return canonical.split(":")[1][:6].upper()

    def get_shortid(self):
        self.shortid = self.get_shortid_for(self._canonical_id())

    def initial(self):
        self.get_properties()
        self.get_uuids()
        self.get_hids()
        self.get_evidences()
        self.get_lots()

    def get_properties(self):
        if self.properties:
            return self.properties

        if self.owner:
            self.properties = SystemProperty.objects.filter(
                owner=self.owner,
                value__in=self._physical_ids(),
            ).order_by("-created")
        else:
            # Is good not filter from owner for public view of device
            self.properties = SystemProperty.objects.filter(
                value=self.id
            ).order_by("-created")

        if self.properties.count():
            self.algorithm = self.properties[0].key
            self.owner = self.properties[0].owner

        return self.properties

    def get_user_properties(self):
        if not self.owner:
            return UserProperty.objects.none()
        return UserProperty.objects.filter(
            owner=self.owner,
            device_id=self._canonical_id(),
            type=UserProperty.Type.USER,
        )

    def get_uuids(self):
        for a in self.get_properties():
            if a.uuid not in self.uuids:
                self.uuids.append(a.uuid)

    @property
    def did(self):
        did_document = CredentialProperty.objects.filter(
            sysprop__in=self.properties,
            key=CredentialProperty.CredentialType.DIDDOC
        ).order_by("created").first()

        return getattr( did_document, "value", "")


    def get_hids(self):
        properties = self.get_properties()

        algos = list(ALGOS.keys())
        algos.append('CUSTOM_ID')
        algos.append('web25')
        self.hids = list(set([x.value for x in properties.filter(
            key__in=algos,
        )]))

        if "custom_id" in self.pk:
            self.hids.append(self.pk)

    def get_evidences(self):
        if not self.uuids:
            self.get_uuids()

        self.evidences = [Evidence(u) for u in self.uuids]

    def get_last_evidence(self):
        if self.last_evidence:
            return self.last_evidence

        fallback_latest = None

        if self.uuid:
            uuid_evidence = Evidence(self.uuid)

            if not uuid_evidence.is_photo_evidence():
                self.last_evidence = uuid_evidence
                return self.last_evidence

            fallback_latest = uuid_evidence

        self.get_evidences()

        if self.evidences:
            if not fallback_latest:
                fallback_latest = self.evidences[-1]

            for evidence in reversed(self.evidences):
                if not evidence.is_photo_evidence():
                    self.last_evidence = evidence
                    return self.last_evidence

        if fallback_latest:
            self.last_evidence = fallback_latest
            return self.last_evidence

        return None


    def is_eraseserver(self):
        if not self.uuids:
            self.get_uuids()
        if not self.uuids:
            return False

        prop = UserProperty.objects.filter(
            uuid__in=self.uuids,
            owner=self.owner,
            type=UserProperty.Type.ERASE_SERVER
        ).first()

        if prop:
            return True
        return False

    def last_uuid(self):
        if self.uuid:
            return self.uuid
        else:
            self.get_uuids()

        return self.uuids[0]

    def get_current_state(self):
        uuid = self.last_uuid()
        return State.objects.filter(snapshot_uuid=uuid).order_by('-date').first()

    def get_lots(self):
        # A lot row may have been stored with either the physical ID or the
        # canonical root. Look up all IDs that belong to this logical device
        # and deduplicate by lot.
        device_ids = self._physical_ids()
        canonical = self._canonical_id()
        if canonical not in device_ids:
            device_ids = [*device_ids, canonical]

        seen = set()
        lots = []
        for dl in (
            DeviceLot.objects.filter(device_id__in=device_ids)
            .select_related("lot__type")
            .order_by("-lot__type__name", "-lot__created")
        ):
            if dl.lot_id in seen:
                continue
            seen.add(dl.lot_id)
            lots.append(dl.lot)
        self.lots = lots

    @classmethod
    def _roots_queryset(cls, institution):
        """Canonical roots owned by ``institution`` ordered by last activity.

        Every ``SystemProperty.value`` has a
        ``RootAlias`` row with ``alias=value``. Therefore the set of
        logical devices equals ``DISTINCT RootAlias.root`` for the owner.
        ``RootAlias.updated`` caches the timestamp of the latest
        ``SystemProperty`` seen for each alias, so the most recent
        activity for a root is ``MAX(updated)`` over its aliases.
        """
        return (
            RootAlias.objects.filter(owner=institution)
            .values("root")
            .annotate(latest=Max("updated"))
            .order_by("-latest")
        )

    @classmethod
    def queryset_orm_unassigned(cls, institution):
        # DeviceLot.device_id stores the canonical root,
        # so excluding ``root IN assigned_roots`` is enough.
        assigned = DeviceLot.objects.filter(
            lot__owner=institution
        ).values_list("device_id", flat=True)
        return (
            cls._roots_queryset(institution)
            .exclude(root__in=assigned)
        )

    @classmethod
    def get_all(cls, institution, offset=0, limit=None):
        qry = cls._roots_queryset(institution)
        rows = qry[offset:] if limit is None else qry[offset:offset+limit]
        count = (
            RootAlias.objects.filter(owner=institution)
            .values("root").distinct().count()
        )
        devices = [cls(id=r["root"], owner=institution) for r in rows]
        return devices, count

    @classmethod
    def get_unassigned(cls, institution, offset=0, limit=20):
        qry = cls.queryset_orm_unassigned(institution)
        rows = qry[offset:] if limit is None else qry[offset:offset+limit]
        assigned = DeviceLot.objects.filter(
            lot__owner=institution
        ).values_list("device_id", flat=True)
        count = (
            RootAlias.objects.filter(owner=institution)
            .exclude(root__in=assigned)
            .values("root").distinct().count()
        )
        devices = [cls(id=r["root"], owner=institution) for r in rows]
        return devices, count


    @classmethod
    def get_properties_from_uuid(cls, uuid, institution):
        ev = SystemProperty.objects.filter(
            owner=institution,
            uuid=uuid
        ).first()
        if ev:
            return cls(id=ev.value, owner=ev.owner, uuid=ev.uuid)

    @property
    def is_websnapshot(self):
        self.get_last_evidence()
        return self.last_evidence.doc['type'] == "WebSnapshot"

    @property
    def last_user_evidence(self):
        self.get_last_evidence()
        return self.last_evidence.doc.get('kv', {}).items()

    @property
    def manufacturer(self):
        self.get_last_evidence()
        return self.last_evidence.get_manufacturer()

    @property
    def updated(self):
        """get timestamp from last evidence created"""
        self.get_last_evidence()
        return self.last_evidence.get_time_created()

    @property
    def serial_number(self):
        self.get_last_evidence()
        return self.last_evidence.get_serial_number()

    @property
    def type(self):
        self.get_last_evidence()
        if self.last_evidence and self.last_evidence.doc.get("type", "") == "WebSnapshot":
            return self.last_evidence.doc.get("device", {}).get("type", "")

        return self.last_evidence.get_chassis()

    @property
    def model(self):
        self.get_last_evidence()
        return self.last_evidence.get_model()

    @property
    def cpu(self):
        self.get_last_evidence()
        return self.last_evidence.get_cpu()

    @property
    def ram(self):
        self.get_last_evidence()
        return self.last_evidence.get_ram()

    @property
    def version(self):
        self.get_last_evidence()
        return self.last_evidence.get_version()

    @property
    def components(self):
        self.get_last_evidence()
        return self.last_evidence.get_components()

    @property
    def did_document(self):
        self.get_last_evidence()
        return self.last_evidence.get_did_document()

    @property
    def status_beneficiary(self):
        if not self.lot:
            return ''

        device_ids = self._physical_ids()
        canonical = self._canonical_id()
        if canonical not in device_ids:
            device_ids = [*device_ids, canonical]

        dev = DeviceBeneficiary.objects.filter(
            device_id__in=device_ids,
            beneficiary__lot=self.lot,
        ).first()

        status = DeviceBeneficiary.Status.AVAILABLE.label
        if dev:
            status = DeviceBeneficiary.Status(dev.status).label

        return status

    @property
    def web_pk(self):
        if self.pk.startswith("custom_id:"):
            for h in self.hids:
                if not h.startswith("custom_id:"):
                    return h

        return self.pk

    @property
    def link_pk(self):
        # Always link to the canonical ID. The canonical root may be a
        # custom_id, a different algorithm's hash (e.g. ereuse26) or the
        # device's own physical ID when it has no alias.
        return self._canonical_id()

    def evidence_export_fields(self):
        """Export fields derived from the device's evidence only.

        Kept separate from relational fields (state, user properties,
        beneficiary status) so a read model can persist this expensive,
        Xapian-backed part without re-parsing evidence on every list/export.

        Each field is read through an Evidence getter that resolves the
        per-format differences internally, so this method just assembles them.
        """
        self.get_last_evidence()
        ev = self.last_evidence

        return {
            'ID': self.shortid or '',
            'manufacturer': self.manufacturer or '',
            'model': self.model or '',
            'serial': self.serial_number or '',
            'cpu_model': ev.get_cpu_model(),
            'cpu_cores': ev.get_cpu_cores(),
            'ram_total': ev.get_ram_total(),
            'ram_type': ev.get_ram_type(),
            'ram_slots': ev.get_ram_slots(),
            'slots_used': ev.get_ram_slots_used(),
            'drive': ev.get_drive(),
            'gpu_model': ev.get_gpu_model(),
            'type': self.type,
            'last_updated': parse_datetime(self.updated) or "",
        }

    def merged_export_fields(self):
        """Evidence-derived export fields, backfilled from older evidence.

        The newest evidence wins; any field it leaves empty is filled from the
        next older evidence, walking back until every field is set or the
        evidence list is exhausted. ``ID`` and ``last_updated`` always come from
        the newest evidence and are never backfilled. An evidence that fails to
        parse (e.g. missing from Xapian) is skipped rather than fatal, so one
        bad evidence never breaks the whole projection.
        """
        self.get_uuids()
        # Walking back through evidences reassigns self.last_evidence; remember
        # the entry state so the device is left pointing at its newest evidence.
        saved_last_evidence = self.last_evidence
        skip = {"ID", "last_updated"}
        merged = None
        remaining = set()
        for uuid in self.uuids:  # ordered newest -> oldest
            try:
                self.last_evidence = Evidence(uuid)
                fields = self.evidence_export_fields()

                is_web_snapshot = (self.last_evidence.is_web_snapshot()
                                   if hasattr(self.last_evidence, 'is_web_snapshot') else False)
                if is_web_snapshot:
                    doc = getattr(self.last_evidence, 'doc', {})
                    kv_data = doc.get('kv', {})
                    fields.update(kv_data)

            except Exception:
                continue
            if merged is None:
                merged = dict(fields)
                remaining = {
                    k for k, v in merged.items()
                    if k not in skip and v in (None, "")
                }
            else:
                for k in list(remaining):
                    v = fields.get(k)
                    if v not in (None, ""):
                        merged[k] = v
                        remaining.discard(k)
            if not remaining:
                break

        self.last_evidence = saved_last_evidence
        if merged is None:
            merged = {"ID": self.shortid or ""}
        return merged

    def storage_readings(self):
        """Per-disk power-on-hours readings across the full evidence history.

        Returns a dict keyed by disk serial number. Each disk carries its
        latest non-empty static metadata plus a ``readings`` list with one
        entry per evidence in which the disk reported power data, deduplicated
        by evidence uuid and ordered oldest -> newest. Raw inxi strings are
        preserved as-is; ``power_on_hours`` is a parsed convenience copy of
        ``power_on``. Stored raw in the projection so the environmental-impact
        calc can reconstruct usage across disk swaps without re-reading Xapian.
        """
        # Local import: environmental_impact.algorithms.common imports
        # device.models, so a module-level import would be circular.
        from environmental_impact.algorithms.common import (
            convert_str_time_to_hours,
        )

        #check best way to input websnapshot storage hours
        if self.is_websnapshot:
            return self.components.get("storage_hours", {})

        self.get_uuids()
        disks = {}
        seen = {}  # serial -> set of uuids already recorded
        for uuid in reversed(list(self.uuids)):  # oldest -> newest
            try:
                evidence = Evidence(uuid)
                components = evidence.get_components()
            except Exception:
                continue
            for c in components:
                if c.get("type") != "Storage":
                    continue
                serial = c.get("serialNumber") or ""
                if not serial:
                    continue
                disk = disks.setdefault(serial, {
                    "model": "",
                    "manufacturer": "",
                    "size": "",
                    "interface": "",
                    "readings": [],
                })
                for key in ("model", "manufacturer", "size", "interface"):
                    v = c.get(key)
                    if v:
                        disk[key] = v

                power_on = c.get("time of used") or ""
                cycles = c.get("cycles") or ""
                health = c.get("health") or ""
                read_units = c.get("read used") or ""
                written_units = c.get("written used") or ""
                if not any((power_on, cycles, health,
                            read_units, written_units)):
                    continue
                recorded = seen.setdefault(serial, set())
                if uuid in recorded:
                    continue
                recorded.add(uuid)
                disk["readings"].append({
                    "uuid": str(uuid),
                    "created": getattr(evidence, "created", None),
                    "power_on": power_on,
                    "power_on_hours": convert_str_time_to_hours(power_on),
                    "cycles": cycles,
                    "health": health,
                    "read_units": read_units,
                    "written_units": written_units,
                })
        return disks

    def components_export(self):
        hardware_info = self.evidence_export_fields()

        user_properties = dict(self.get_user_properties().values_list("key", "value"))

        hardware_info.update({
            'user_properties': user_properties,
            'current_state': self.get_current_state().state if self.get_current_state() else '',
            'last_updated': parse_datetime(self.updated) or "",
            'beneficiary_status': self.status_beneficiary or ""
        })

        if not self.last_evidence.is_legacy or not self.last_evidence:
            return hardware_info

        if getattr(self.last_evidence, 'is_web_snapshot', False):
            doc = getattr(self.last_evidence, 'doc', {})
            kv_data = doc.get('kv', {})

            hardware_info.update(kv_data)

            return hardware_info

        storage_devices = []
        gpu_models = []
        slots_used = slots_total = 0

        for c in self.components:
            match c.get("type"):
                case "Motherboard":
                    hardware_info.update({
                        'manufacturer': c.get("manufacturer", ""),
                        'serial': self.serial_number,
                        'ram_total': c.get("installedRam", ""),
                    })
                case "Processor":
                    hardware_info.update({
                        'cpu_cores': c.get("cores", ""),
                        'cpu_model': c.get("model", "")
                    })
                case "RamModule":
                    slots_total += 1
                    if slots_used == 0:
                        hardware_info.update({
                            'ram_type': c.get("interface", "")
                        })
                    if c.get("interface", "") != "no module installed":
                        slots_used += 1
                case "Storage":
                    if size := c.get("size", ""):
                        storage_devices.append({
                            'model': c.get("model", ""),
                            'size': size,
                            'type': c.get("interface", "")
                        })
                case "GraphicCard":
                    if model := c.get("model", ""):
                        gpu_models.append(model)

        if storage_devices:
            hardware_info['drive'] = ", ".join([f" {d['type']} {d['model']} ({d['size']} )"
                                            for d in storage_devices])
        if gpu_models:
            hardware_info['gpu_model'] = ", ".join(gpu_models)

        hardware_info.update({
            'slots_used': slots_used,
            'ram_slots': slots_total,
        })

        return hardware_info

    def get_label_data(self, request, settings=None):
        if not settings:
            settings, created= InstitutionLabelSettings.objects.get_or_create(institution=self.owner)

        if settings.qr_label_version == LabelVersion.V1:
            return {
                'payload': self.shortid,
            }

        if settings.qr_content_type == QRContentType.NONE:
            qr_payload = ""

        elif settings.qr_content_type == QRContentType.PUBLIC_VIEW:
            path = reverse('device:device_web', kwargs={'pk': self.pk})
            qr_payload = request.build_absolute_uri(path)

        elif settings.qr_content_type == QRContentType.DEVICE_INVENTORY:
            path = reverse('device:details', kwargs={'pk': self.pk})
            qr_payload = request.build_absolute_uri(path)

        elif settings.qr_content_type == QRContentType.DPP_URL:
            path = reverse('device:dpp', kwargs={'pk': self.pk})
            qr_payload = request.build_absolute_uri(path)

        elif settings.qr_content_type == QRContentType.DID:
            if self.did:
                qr_payload = self.did
            else:
                qr_payload = self.shortid
        else:
            qr_payload = str(self.shortid)

        TRANSLATED_PROPERTIES = {
            'ID': _('Short ID'),
            'manufacturer': _('Manufacturer'),
            'model': _('Model'),
            'serial': _('Serial Number'),
            'cpu_model': _('CPU Model'),
            'ram_total': _('Total RAM'),
            'ram_type': _('RAM Type'),
            'drive': _('Storage Drive'),
            'type': _('Device Type'),
        }

        export_data = self.components_export()
        properties = []

        for prop in settings.qr_printed_properties:
            val = export_data.get(prop, _('N/A'))

            name = TRANSLATED_PROPERTIES.get(prop, prop.replace('_', ' ').title())

            properties.append({'name': name, 'value': val})

        return {
            'payload': qr_payload,
            'properties': properties,
            'include_logo': settings.qr_include_logo,
            'logo_url': self.owner.logo if settings.qr_include_logo and self.owner.logo else None,
        }

# Registers the ProductCache ORM model under the `device` app. Django only
# auto-imports `<app>.models`, so the read model defined in device/product_cache.py
# must be imported here to be discovered by makemigrations.
from device.product_cache import ProductCache  # noqa: E402,F401

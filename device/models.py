from django.db import models
from django.db.models import Max
from django.urls import reverse

from utils.constants import ALGOS
from evidence.models import SystemProperty, UserProperty, Evidence, RootAlias
from django.utils.dateparse import parse_datetime
from lot.models import DeviceLot, DeviceBeneficiary
from action.models import State
from user.models import InstitutionSettings, LabelVersion, QRContentType

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

    def __init__(self, *args, **kwargs):
        # the id is the chid of the device
        # in the rootalias table id is the root
        self.id = kwargs["id"]
        self.uuid = kwargs.get("uuid")
        self.lot = kwargs.get("lot")
        self.pk = self.id
        self.hid = self.id.split(":")[1]
        self.algorithm = None
        self.alias = None
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
        """Resolve self.id to its canonical device ID via RootAlias.

        Thanks to invariant (every SystemProperty.value has a
        RootAlias row with alias=value), any physical ID resolves through one
        lookup; a custom_id or unknown ID falls back to itself.
        """
        if self._canonical_cache is not None:
            return self._canonical_cache
        if not self.owner:
            self._canonical_cache = self.id
            return self._canonical_cache

        self.alias = RootAlias.objects.filter(
            owner=self.owner, alias=self.id
        ).first()
        self._canonical_cache = self.alias.root if self.alias else self.id
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

    def get_shortid(self):
        canonical = self._canonical_id()
        self.shortid = canonical.split(":")[1][:6].upper()

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
            return

        if self.uuid:
            self.last_evidence = Evidence(self.uuid)
            return

        properties = self.get_properties()
        if not properties.count():
            return
        prop = properties.first()

        self.last_evidence = Evidence(prop.uuid)

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

    def matches_query(self, query):
        if not query:
            return True

        #thanks ai for usage of lambda for lazy compute
        details = {
            'shortid': lambda d: str(d.shortid),
            'type': lambda d: str(getattr(d, 'type', '')),
            'manufacturer': lambda d: str(getattr(d, 'manufacturer', '')),
            'model': lambda d: str(getattr(d, 'model', '')),
            'current_state': lambda d: str(d.get_current_state()) if d.get_current_state() else '',
            'status_beneficiary': lambda d: str(d.status_beneficiary),
            'serial': lambda d: str(getattr(d, 'serial_number', '')),
            'cpu': lambda d: str(getattr(d, 'cpu', '')),
            'total_ram': lambda d: str(getattr(d, 'total_ram', ''))
        }

        #if query ends with :some_field, only search on this field
        if ':' in query:
            search_part, field_part = query.rsplit(':', 1)
            search_part = search_part.strip().lower()
            field_part = field_part.strip().lower()

            if field_part in details:
                field_value = details[field_part](self).lower()
                return search_part in field_value
            return False

        query = query.lower().strip()

        for value in details.values():
            if query in value(self).lower():
                return True

        for prop in self.get_user_properties():
            if query in str(prop.key).lower():
                return True
            if query in str(prop.value).lower():
                return True

        return False

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
        if self.last_evidence.doc['type'] == "WebSnapshot":
            return self.last_evidence.doc.get("device", {}).get("type", "")

        return self.last_evidence.get_chassis()

    @property
    def model(self):
        self.get_last_evidence()
        return self.last_evidence.get_model()

    @property
    def cpu(self):
        cpu_component = next(
            (c for c in self.components if c.get('type') == 'Processor'),
            None
        )
        cpu_model = cpu_component.get('model', '') if cpu_component else ""
        return cpu_model

    @property
    def total_ram(self):
        ram_component = next(
            (c for c in self.components if c.get('type') == 'RamModule'),
            None
        )
        return ram_component.get('total_ram', '') if ram_component else ""

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

    def components_export(self):
        self.get_last_evidence()

        user_properties = ""
        for x in self.get_user_properties():
            user_properties += "({}:{}) ".format(x.key, x.value)

        hardware_info = {
            'ID': self.shortid or '',
            'manufacturer': self.manufacturer or '',
            'model': self.model or '',
            'serial': '',
            'cpu_model': '',
            'cpu_cores': '',
            'ram_total': '',
            'ram_type': '',
            'ram_slots': '',
            'slots_used': '',
            'drive': '',
            'gpu_model': '',
            'type': self.type,
            'user_properties': user_properties,
            'current_state': self.get_current_state().state if self.get_current_state() else '',
            'last_updated': parse_datetime(self.updated) or "",
            'beneficiary_status': self.status_beneficiary or ""
        }

        if not self.last_evidence.is_legacy or not self.last_evidence:
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
            settings, created= InstitutionSettings.objects.get_or_create(institution=self.owner)

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

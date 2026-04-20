import qrcode
import base64

from io import BytesIO
from django.db import models
from django.db.models import Subquery, F, Window, Max, Q, Exists, OuterRef
from django.db.models.functions import RowNumber

from utils import sql_query as q_sql
from utils.constants import ALGOS
from evidence.models import SystemProperty, UserProperty, Evidence, RootAlias, get_custom_id_uuid
from django.utils.dateparse import parse_datetime
from lot.models import DeviceLot, DeviceBeneficiary
from action.models import State


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
        self.get_shortid()
        self.get_last_evidence()

    def get_shortid(self):
        self.shortid = self.pk.split(":")[1][:6].upper()
        if self.owner:
            self.alias = RootAlias.objects.filter(
                owner=self.owner,
                alias=self.pk
            ).first()
            if self.alias:
                self.shortid = self.alias.root.split(":")[1][:6].upper()

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
            # if hid exist as root
            roots = [x.alias for x in RootAlias.objects.filter(root=self.id, owner=self.owner)]
            roots.append(self.id)
            # if hid exist as alias
            ali = RootAlias.objects.filter(alias=self.id).first()
            if ali:
                roots.append(ali.root)
                for x in RootAlias.objects.filter(root=ali.root, owner=self.owner):
                    if x.alias not in roots:
                        roots.append(x.alias)

            self.properties = SystemProperty.objects.filter(
                owner=self.owner,
                value__in=roots
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
        if not self.uuids:
            self.get_uuids()

        uuids = list(self.uuids)

        # Include the stable custom_id UUID so properties stored directly on the
        # custom_id entity are always found, regardless of which aliases exist.
        if self.id.startswith("custom_id:") and self.owner:
            uuids.append(get_custom_id_uuid(self.owner.pk, self.id))
        elif self.owner:
            ali = RootAlias.objects.filter(alias=self.id, owner=self.owner).first()
            if ali and ali.root.startswith("custom_id:"):
                uuids.append(get_custom_id_uuid(self.owner.pk, ali.root))

        user_properties = UserProperty.objects.filter(
            uuid__in=uuids,
            owner=self.owner,
            type=UserProperty.Type.USER,
        )
        return user_properties

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

        return self.uuids[0] if self.uuids else None

    def get_current_state(self):
        uuid = self.last_uuid()
        if not uuid:
            return None
        return State.objects.filter(snapshot_uuid=uuid).order_by('-date').first()

    def get_lots(self):
        # Build the set of device_ids to look up in DeviceLot.
        # New records store the custom_id directly; old records may use an ereuse24
        # alias — we include all aliases for backward compatibility.
        device_ids = [self.id]

        if self.id.startswith("custom_id:") and self.owner:
            for ra in RootAlias.objects.filter(root=self.id, owner=self.owner):
                device_ids.append(ra.alias)
        elif self.owner:
            ali = RootAlias.objects.filter(alias=self.id, owner=self.owner).first()
            if ali and ali.root.startswith("custom_id:"):
                device_ids.append(ali.root)
                for ra in RootAlias.objects.filter(root=ali.root, owner=self.owner):
                    device_ids.append(ra.alias)

        seen = set()
        lots = []
        for dl in DeviceLot.objects.filter(device_id__in=device_ids).select_related(
            'lot__type'
        ).order_by('-lot__type__name', '-lot__created'):
            if dl.lot_id not in seen:
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

    @staticmethod
    def filter_valid_ids(queryset, device_id_field, owner, deduplicate=False):
        """Filter a queryset excluding orphaned custom_id devices.

        An orphaned custom_id is one that no longer has any RootAlias pointing
        to it (i.e. the alias was deleted). Regular non-custom_id devices are
        always kept.

        When deduplicate=True, entries that share the same canonical custom_id
        root are collapsed to one (keeping the first seen). Returns a queryset
        filtered by PK.

        Usage:
            Device.filter_valid_ids(DeviceLot.objects.all(), 'device_id', owner)
            Device.filter_valid_ids(qs, 'device_id', owner, deduplicate=True)
        """
        has_alias = RootAlias.objects.filter(
            root=OuterRef(device_id_field), owner=owner
        )
        valid_qs = queryset.annotate(
            _has_alias=Exists(has_alias)
        ).filter(
            Q(_has_alias=True) | ~Q(**{f'{device_id_field}__startswith': 'custom_id:'})
        )

        if not deduplicate:
            return valid_qs

        entries = list(valid_qs.values('pk', device_id_field))
        raw_ids = [e[device_id_field] for e in entries]
        alias_map = dict(
            RootAlias.objects.filter(owner=owner, alias__in=raw_ids)
            .values_list('alias', 'root')
        )
        seen = set()
        keep_pks = []
        for entry in entries:
            did = entry[device_id_field]
            canonical = alias_map.get(did, did)
            if canonical not in seen:
                seen.add(canonical)
                keep_pks.append(entry['pk'])

        return queryset.filter(pk__in=keep_pks)

    @classmethod
    def queryset_orm(cls, institution):
        alias = RootAlias.objects.filter(owner=institution)
        sp = SystemProperty.objects.filter(owner=institution)

        # qry1 = Search roots in RootAlias than not exist in Systemproperty
        # qry2 = Search the first entry alias for every one root of qry1
        # qry3 = Search all alias in RootAlias than not exists in qry2
        # qry4 = Search all values in Systemproperty than not exists in qry3

        qry1 = alias.exclude(root__in=sp.values_list("value", flat=True))

        #######
        ranked_qs = qry1.annotate(
            rank=Window(
                expression=RowNumber(),
                partition_by=[F('root')],
                order_by=[F('id')]
            )
        ).filter(
            rank=1
        ).values_list('pk', flat=True).distinct()

        qry2 = alias.filter(
            pk__in=Subquery(ranked_qs)).values_list("alias", flat=True).distinct()

        # only for postgresql
        # qry2 = alias.filter(root__in=qry1).order_by('root', 'id').distinct('root').values_list(
        #     "alias", flat=True
        # ).distinct()
        #######
        qry3 = alias.exclude(alias__in=qry2).values_list("alias", flat=True).distinct()
        qry4 = sp.exclude(value__in=qry3).values('value').annotate(max_created=Max('created'))
        qry5 = qry4.order_by("-max_created").values_list('value', flat=True)
        return qry5

    @classmethod
    def queryset_orm_unassigned(cls, institution):
        qry4 = cls.queryset_orm(institution)
        alias = RootAlias.objects.filter(owner=institution)
        dev_lots = DeviceLot.objects.filter(lot__owner=institution
                                            ).values_list("device_id", flat=True).distinct()
        root_lots = alias.filter(root__in=dev_lots).values_list("alias", flat=True).distinct()
        alias_lots = alias.filter(alias__in=dev_lots).values_list("alias", flat=True).distinct()

        # excluding devices and alias linked to lots
        exclude_lots = qry4.exclude(
            value__in=dev_lots
        ).exclude(
            value__in=root_lots
        ).exclude(
            value__in=alias_lots
        ).distinct()
        return exclude_lots

    @classmethod
    def get_all(cls, institution, offset=0, limit=None):
        # return cls.get_all_sql(institution, offset=offset, limit=limit)
        return cls.get_all_orm(institution, offset=offset, limit=limit)

    @classmethod
    def get_unassigned(cls, institution, offset=0, limit=20):
        # return cls.get_unassigned_sql(institution, offset=offset, limit=limit)
        return cls.get_unassigned_orm(institution, offset=offset, limit=limit)

    @classmethod
    def get_all_orm(cls, institution, offset=0, limit=None):
        qry = cls.queryset_orm(institution)
        evs = qry[offset:] if limit is None else qry[offset:offset+limit]
        count = qry.count()
        devices = [cls(id=x, owner=institution) for x in evs]
        return devices, count

    @classmethod
    def get_unassigned_orm(cls, institution, offset=0, limit=20):
        qry = cls.queryset_orm_unassigned(institution)
        evs = qry[offset:] if limit is None else qry[offset:offset+limit]
        count = qry.count()
        devices = [cls(id=x, owner=institution) for x in evs]
        return devices, count

    @classmethod
    def get_all_sql(cls, institution, offset=0, limit=None):
        evs = q_sql.queryset_SQL(institution, offset=offset, limit=limit)
        count = q_sql.queryset_SQL_count(institution)
        devices = [cls(id=x[0], owner=institution) for x in evs]
        return devices, count

    @classmethod
    def get_unassigned_sql(cls, institution, offset=0, limit=20):
        evs = q_sql.queryset_SQL_unassigned(institution, offset=offset, limit=limit)
        count = q_sql.queryset_SQL_unassigned_count(institution)
        devices = [cls(id=x[0], owner=institution) for x in evs]
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

        # New records store the custom_id directly; old records may use an ereuse24
        # alias — check all possibilities for backward compatibility.
        device_ids = [self.id]

        if self.id.startswith("custom_id:") and self.owner:
            for ra in RootAlias.objects.filter(root=self.id, owner=self.owner):
                device_ids.append(ra.alias)
        elif self.owner:
            ali = RootAlias.objects.filter(alias=self.id, owner=self.owner).first()
            if ali and ali.root.startswith("custom_id:"):
                device_ids.append(ali.root)
                for ra in RootAlias.objects.filter(root=ali.root, owner=self.owner):
                    device_ids.append(ra.alias)

        dev = DeviceBeneficiary.objects.filter(
            device_id__in=device_ids,
            beneficiary__lot=self.lot
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
        if self.alias and self.alias.root.startswith("custom_id:"):
            return self.alias.root
        return self.pk

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
            'last_updated': parse_datetime(self.updated) or ""
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

    @property
    def QR(self):
        if hasattr(self, "img_qr"):
            return self.img_qr

        qr = qrcode.QRCode(
            version=1,            # Size of QR 1 to 40
            error_correction=qrcode.constants.ERROR_CORRECT_L, # Level of correct errors
            box_size=10,          # Pixels for every box of QR
            border=1,             # Size of border
        )

        qr.add_data(self.shortid)
        qr.make(fit=True)

        # Custom colors with names or hexa
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        self.img_qr = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return self.img_qr

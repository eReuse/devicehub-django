from django.db import models, connection
from django.conf import settings

from utils.constants import ALGOS
from evidence.models import SystemProperty, UserProperty, Evidence, RootAlias
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
        self.algorithm = None
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
        self.shortid = self.pk[:6].upper()
        if self.owner:
            alias = RootAlias.objects.filter(
                owner=self.owner,
                alias=self.pk
            ).first()
            if alias:
                self.shortid = alias.root

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
                for x in RootAlias.objects.filter(root=ali.root, owner=self.owner):
                    if x.alias not in roots:
                        roots.append(x.alias)

            self.properties = SystemProperty.objects.filter(
                owner=self.owner,
                value__in=roots
            ).order_by("-created")
        else:
            # TODO is good not filter from owner?
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

        user_properties = UserProperty.objects.filter(
            uuid__in=self.uuids,
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
        self.hids = list(set(properties.filter(
            key__in=algos,
        ).values_list("value", flat=True)))

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
        self.lots = [
            x.lot for x in DeviceLot.objects.filter(device_id=self.id)
            .select_related('lot__type')
            .order_by('-lot__type__name', '-lot__created')
        ]

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
    def queryset_pgsql(cls, institution):
        alias = RootAlias.objects.filter(owner=institution)
        sp = SystemProperty.objects.filter(owner=institution)

        # Search roots in RootAlias than not exist in Systemproperty
        # Search the first entry alias for every one root of qry1
        # Search all alias in RootAlias than not exists in qry2
        # Search all values in Systemproperty than not exists in qry3
        qry1 = alias.exclude(root__in=sp.values("value")).values_list("root", flat=True).distinct()
        qry2 = alias.filter(root__in=qry1).order_by('root', 'id').distinct('root').values_list(
            "alias", flat=True
        ).distinct()
        qry3 = alias.exclude(alias_in=qry2).values_list("alias", flat=True).distinct()
        qry4 = sp.exclude(value__in=qry3).order_by("-created")
        return qry4

    @classmethod
    def queryset_SQL(cls, institution, offset=0, limit=None):
        institution_id = institution.id

        # Search roots in RootAlias than not exist in Systemproperty
        qry1 = f"""
            select distinct root from evidence_rootalias as al
            where al.owner_id = {institution_id} and not exists (
                select 1
                from evidence_systemproperty as sp
                where al.root = sp.value and sp.owner_id = {institution_id}
                and al.owner_id = {institution_id}
            )
        """
        # Search the first entry alias for every one root of qry1
        qry2 = f"""
            select alias from (
                select alias, root, row_number() over (
                    partition by root order by id asc
                ) as row_num from evidence_rootalias as _root
                where _root.owner_id = {institution_id}
            ) as subquery
            where row_num = 1 and root in ({qry1})
        """
        # Search all alias in RootAlias than not exists in qry2
        qry3 = f"""
            select distinct ali.alias from evidence_rootalias as ali
            where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
        """
        # Search all values in Systemproperty than not exists in qry3
        sql = f"""
            select distinct sp.value from evidence_systemproperty as sp
            where sp.value not in ({qry3}) and sp.owner_id = {institution_id}
        """

        if limit:
            sql += " limit {} offset {}".format(int(limit), int(offset))

        sql += ";"

        annotations = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            annotations = cursor.fetchall()

        return annotations

    @classmethod
    def queryset_SQL_count(cls, institution):
        institution_id = institution.id

        # Search roots in RootAlias than not exist in Systemproperty
        qry1 = f"""
            select distinct root from evidence_rootalias as al
            where al.owner_id = {institution_id} and not exists (
                select 1
                from evidence_systemproperty as sp
                where al.root = sp.value and sp.owner_id = {institution_id}
                and al.owner_id = {institution_id}
            )
        """
        # Search the first entry alias for every one root of qry1
        qry2 = f"""
            select alias from (
                select alias, root, row_number() over (
                    partition by root order by id asc
                ) as row_num from evidence_rootalias as _root
                where _root.owner_id = {institution_id}
            ) as subquery
            where row_num = 1 and root in ({qry1})
        """
        # Search all alias in RootAlias than not exists in qry2
        qry3 = f"""
            select distinct ali.alias from evidence_rootalias as ali
            where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
        """
        # Search all values in Systemproperty than not exists in qry3
        sql = f"""
         select count(distinct sp.value) from evidence_systemproperty as sp
            where sp.value not in ({qry3}) and sp.owner_id = {institution_id};
        """

        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()[0][0]

    @classmethod
    def queryset_SQL_unassigned(cls, institution, offset=0, limit=None):
        institution_id = institution.id

        # Search roots in RootAlias than not exist in Systemproperty
        qry1 = f"""
            select distinct root from evidence_rootalias as al
            where al.owner_id = {institution_id} and not exists (
                select 1
                from evidence_systemproperty as sp
                where al.root = sp.value and sp.owner_id = {institution_id}
                and al.owner_id = {institution_id}
            )
        """
        # Search the first entry alias for every one root of qry1
        qry2 = f"""
            select alias from (
                select alias, root, row_number() over (
                    partition by root order by id asc
                ) as row_num from evidence_rootalias as _root
                where _root.owner_id = {institution_id}
            ) as subquery
            where row_num = 1 and root in ({qry1})
        """
        # Search all alias in RootAlias than not exists in qry2
        qry3 = f"""
            select distinct ali.alias from evidence_rootalias as ali
            where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
        """
        device_lots = f"""
            select device_id from lot_devicelot as ld left join lot_lot as lot on ld.lot_id=lot.id
              where lot.owner_id = {institution_id}
        """
        alias_of_hids_in_lots = f"""
            select mp.alias from evidence_rootalias as mp
              where mp.owner_id={institution_id} and mp.root in (
                select distinct root from evidence_rootalias as ra
                  where ra.owner_id={institution_id} and (ra.alias in (
                    select device_id from lot_devicelot as ld
                      left join lot_lot as lot on ld.lot_id=lot.id
                    where lot.owner_id = {institution_id}
                  ) or ra.root in (
                    select device_id from lot_devicelot as ld
                      left join lot_lot as lot on ld.lot_id=lot.id
                    where lot.owner_id = {institution_id}
                  )
                )
            )
        """
        # Search all values in Systemproperty than not exists in qry3
        sql = f"""
            select distinct sp.value from evidence_systemproperty as sp
            where
              sp.value not in ({qry3}) and
              sp.value not in ({device_lots}) and
              sp.value not in ({alias_of_hids_in_lots}) and
              sp.owner_id = {institution_id}
        """
        if limit:
            sql += " limit {} offset {}".format(int(limit), int(offset))

        sql += ";"

        annotations = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            annotations = cursor.fetchall()

        return annotations

    @classmethod
    def queryset_SQL_unassigned_count(cls, institution):
        institution_id = institution.id

        # Search roots in RootAlias than not exist in Systemproperty
        qry1 = f"""
            select distinct root from evidence_rootalias as al
            where al.owner_id = {institution_id} and not exists (
                select 1
                from evidence_systemproperty as sp
                where al.root = sp.value and sp.owner_id = {institution_id}
                and al.owner_id = {institution_id}
            )
        """
        # Search the first entry alias for every one root of qry1
        qry2 = f"""
            select alias from (
                select alias, root, row_number() over (
                    partition by root order by id asc
                ) as row_num from evidence_rootalias as _root
                where _root.owner_id = {institution_id}
            ) as subquery
            where row_num = 1 and root in ({qry1})
        """
        # Search all alias in RootAlias than not exists in qry2
        qry3 = f"""
            select distinct ali.alias from evidence_rootalias as ali
            where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
        """
        device_lots = f"""
            select device_id from lot_devicelot as ld left join lot_lot as lot on ld.lot_id=lot.id
              where lot.owner_id = {institution_id}
        """
        # Search all values in Systemproperty than not exists in qry3
        sql = f"""
            select count(distinct sp.value) from evidence_systemproperty as sp
            where
              sp.value not in ({qry3}) and
              sp.value not in ({device_lots}) and
              sp.owner_id = {institution_id};
        """

        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()[0][0]

    @classmethod
    def get_all(cls, institution, offset=0, limit=None):
        engine = settings.DATABASES.get("default", {}).get("ENGINE")
        if 'django.db.backends.postgresql' == engine:
            qry = cls.queryset_pgsql(institution)
            evs = qry[offset:offset+limit]
            count = qry.count()
        else:
            evs = cls.queryset_SQL(institution, offset=offset, limit=limit)
            count = cls.queryset_SQL_count(institution)

        devices = [cls(id=x[0], owner=institution) for x in evs]
        return devices, count

    @classmethod
    def get_unassigned(cls, institution, offset=0, limit=20):
        engine = settings.DATABASES.get("default", {}).get("ENGINE")
        if 'django.db.backends.postgresql' == engine:
            device_lots = DeviceLot.objects.filter(lot__owner=institution).values("device_id").distinct()
            qry = cls.queryset_pgsql(institution).exclude(value__in=device_lots)
            evs = qry[offset:offset+limit]
            count = qry.count()
        else:
            evs = cls.queryset_SQL_unassigned(institution, offset=offset, limit=limit)
            count = cls.queryset_SQL_unassigned_count(institution)

        devices = [cls(id=x[0], owner=institution) for x in evs]
        return devices, count


    @classmethod
    def get_properties_from_uuid(cls, uuid, institution):
        ev = SystemProperty.objects.filter(
            owner=institution,
            uuid=uuid
        ).first()
        if ev:
            return cls(id=ev)

    @property
    def is_websnapshot(self):
        self.get_last_evidence()
        return self.last_evidence.doc['type'] == "WebSnapshot"

    @property
    def last_user_evidence(self):
        self.get_last_evidence()
        return self.last_evidence.doc['kv'].items()

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

        dev = DeviceBeneficiary.objects.filter(
            device_id=self.id,
            beneficiary__lot=self.lot
        ).first()

        status = DeviceBeneficiary.Status.AVAILABLE.label
        if dev:
            status = DeviceBeneficiary.Status(dev.status).label

        return status

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
                        'serial': c.get("serialNumber", ""),
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

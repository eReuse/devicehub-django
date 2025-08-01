from django.db import models, connection

from utils.constants import ALGOS
from evidence.models import SystemProperty, UserProperty, Evidence
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
        self.id = kwargs["id"]
        self.uuid = kwargs.get("uuid")
        self.lot = kwargs.get("lot")
        self.pk = self.id
        self.shortid = self.pk[:6].upper()
        self.algorithm = None
        self.owner = None
        self.properties = []
        self.hids = []
        self.uuids = []
        self.evidences = []
        self.lots = []
        self.last_evidence = None
        self.get_last_evidence()

    def initial(self):
        self.get_properties()
        self.get_uuids()
        self.get_hids()
        self.get_evidences()
        self.get_lots()

    def get_properties(self):
        if self.properties:
            return self.properties

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
    def get_all(cls, institution, offset=0, limit=None):
        sql = """
            WITH RankedProperties AS (
                SELECT
                    t1.value,
                    t1.key,
                    t1.created,
                    ROW_NUMBER() OVER (
                        PARTITION BY t1.uuid
                        ORDER BY
                            CASE
                                WHEN t1.key = 'CUSTOM_ID' THEN 1
                                WHEN t1.key = '{algorithm}' THEN 2
                            END,
                            t1.created DESC
                    ) AS row_num
                FROM evidence_systemproperty AS t1
                WHERE t1.owner_id = {institution}
                  AND t1.key IN ('CUSTOM_ID', '{algorithm}')
            )
            SELECT DISTINCT
                value
            FROM
                RankedProperties
            WHERE
                row_num = 1
            ORDER BY created DESC
        """.format(
            institution=institution.id,
            algorithm=institution.algorithm,
        )
        if limit:
            sql += " limit {} offset {}".format(int(limit), int(offset))

        sql += ";"

        annotations = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            annotations = cursor.fetchall()

        devices = [cls(id=x[0]) for x in annotations]
        count = cls.get_all_count(institution)
        return devices, count

    @classmethod
    def get_all_count(cls, institution):

        sql = """
            WITH RankedProperties AS (
                SELECT
                    t1.value,
                    t1.key,
                    t1.created,
                    ROW_NUMBER() OVER (
                        PARTITION BY t1.uuid
                        ORDER BY
                            CASE
                                WHEN t1.key = 'CUSTOM_ID' THEN 1
                                WHEN t1.key = '{algorithm}' THEN 2
                            END,
                            t1.created DESC
                    ) AS row_num

                FROM evidence_systemproperty AS t1
               WHERE t1.owner_id = {institution}
                  AND t1.key IN ('CUSTOM_ID', '{algorithm}')
            )
            SELECT
                COUNT(DISTINCT value)
            FROM
                RankedProperties
            WHERE
                row_num = 1
            ORDER BY created DESC
        """.format(
            institution=institution.id,
            algorithm=institution.algorithm
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()[0][0]


    @classmethod
    def get_unassigned(cls, institution, offset=0, limit=None):

        sql = """
            WITH RankedProperties AS (
                SELECT
                    t1.value,
                    t1.key,
                    t1.created,
                    ROW_NUMBER() OVER (
                        PARTITION BY t1.uuid
                        ORDER BY
                            CASE
                                WHEN t1.key = 'CUSTOM_ID' THEN 1
                                WHEN t1.key = '{algorithm}' THEN 2
                            END,
                            t1.created DESC
                    ) AS row_num
                FROM evidence_systemproperty AS t1
                LEFT JOIN lot_devicelot AS t2 ON t1.value = t2.device_id
                WHERE t2.device_id IS NULL
                  AND t1.owner_id = {institution}
                  AND t1.key IN ('CUSTOM_ID', '{algorithm}')
            )
            SELECT DISTINCT
                value
            FROM
                RankedProperties
            WHERE
                row_num = 1
            ORDER BY created DESC
        """.format(
            institution=institution.id,
            algorithm=institution.algorithm
        )
        if limit:
            sql += " limit {} offset {}".format(int(limit), int(offset))

        sql += ";"

        properties = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            properties = cursor.fetchall()

        devices = [cls(id=x[0]) for x in properties]
        count = cls.get_unassigned_count(institution)
        return devices, count

    @classmethod
    def get_unassigned_count(cls, institution):

        sql = """
            WITH RankedProperties AS (
                SELECT
                    t1.value,
                    t1.key,
                    t1.created,
                    ROW_NUMBER() OVER (
                        PARTITION BY t1.uuid
                        ORDER BY
                            CASE
                                WHEN t1.key = 'CUSTOM_ID' THEN 1
                                WHEN t1.key = '{algorithm}' THEN 2
                            END,
                            t1.created DESC
                    ) AS row_num
                FROM evidence_systemproperty AS t1
                LEFT JOIN lot_devicelot AS t2 ON t1.value = t2.device_id
                WHERE t2.device_id IS NULL
                  AND t1.owner_id = {institution}
                  AND t1.key IN ('CUSTOM_ID', '{algorithm}')
            )
            SELECT
                COUNT(DISTINCT value)
            FROM
                RankedProperties
            WHERE
                row_num = 1
            ORDER BY created DESC
        """.format(
            institution=institution.id,
            algorithm=institution.algorithm
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()[0][0]

    @classmethod
    def get_properties_from_uuid(cls, uuid, institution):
        sql = """
            WITH RankedProperties AS (
                SELECT
                    t1.value,
                    t1.key,
                    t1.created,
                    ROW_NUMBER() OVER (
                        PARTITION BY t1.uuid
                        ORDER BY
                            CASE
                                WHEN t1.key = 'CUSTOM_ID' THEN 1
                                WHEN t1.key = '{algorithm}' THEN 2
                            END,
                            t1.created DESC
                    ) AS row_num
                FROM evidence_systemproperty AS t1
                WHERE t1.owner_id = {institution}
                  AND t1.uuid = '{uuid}'
                  AND t1.key IN ('CUSTOM_ID', '{algorithm}')
            )
            SELECT DISTINCT
                value
            FROM
                RankedProperties
            WHERE
                row_num = 1
            ORDER BY created DESC
        """.format(
            uuid=uuid.replace("-", ""),
            institution=institution.id,
            algorithm=institution.algorithm,
        )

        properties = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            properties = cursor.fetchall()

        return cls(id=properties[0][0])

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

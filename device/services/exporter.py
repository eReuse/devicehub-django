import csv
import re
from io import BytesIO

from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from openpyxl import Workbook

from evidence.models import UserProperty
from lot.models import DeviceBeneficiary


class DeviceExportService:
    EXPORT_CHUNK_SIZE = 1000
    HEADERS = [
        'ID', 'type', 'manufacturer', 'model', 'cpu_model', 'cpu_cores', 'current_state',
        'ram_total', 'ram_type', 'ram_slots', 'slots_used', 'drive', 'gpu_model',
        'user_properties', 'serial', 'last_updated', 'beneficiary_status',
    ]

    def __init__(self, institution, device_qs, request_get, base_name="devices_export"):
        self.institution = institution
        self.device_qs = device_qs
        self.request_get = request_get
        self.base_name = base_name

    def _get_filename(self):
        base_name = re.sub(r'[\s/\\,;:|]+', '_', self.base_name.strip())
        base_name = re.sub(r'[^a-zA-Z0-9\-_]', '', base_name)
        date_str = timezone.now().strftime("%Y-%m-%d")

        exclude_params = {'_export', 'limit', 'page', 'sort'}
        filter_parts = []

        for key, v_list in self.request_get.lists():
            if key in exclude_params:
                continue
            clean_key = re.sub(r'[^a-zA-Z0-9]', '', key)
            for val in v_list:
                clean_val = re.sub(r'[^a-zA-Z0-9\-_]', '', val.strip().replace('__', ''))
                if clean_val:
                    filter_parts.append(f"{clean_key}-{clean_val}")

        filter_str = "_".join(filter_parts)
        if len(filter_str) > 60:
            filter_str = f"{filter_str[:57]}..."

        return f"{base_name}_{filter_str}_{date_str}" if filter_str else f"{base_name}_{date_str}"

    def _iter_export_rows(self):
        available = str(DeviceBeneficiary.Status.AVAILABLE.label)
        total_count = self.device_qs.count()
        qs_ordered = self.device_qs.order_by('root')

        for i in range(0, total_count, self.EXPORT_CHUNK_SIZE):
            chunk_qs = list(qs_ordered[i:i + self.EXPORT_CHUNK_SIZE])
            chunk_ids = [p.root for p in chunk_qs]

            # side-load User properties to avoid N+1 queries
            user_props = {}
            up_qs = UserProperty.objects.filter(
                owner=self.institution,
                device_id__in=chunk_ids,
                type=UserProperty.Type.USER,
            ).values('device_id', 'key', 'value')

            for up in up_qs:
                user_props.setdefault(up['device_id'], []).append(f"({up['key']}:{up['value']}) ")

            for p in chunk_qs:
                data = p.data or {}
                state = getattr(p, 'current_state_annotated', '')
                status = getattr(p, 'beneficiary_status_annotated', None)

                last_updated = p.last_updated
                if last_updated and timezone.is_aware(last_updated):
                    last_updated = timezone.make_naive(last_updated)

                yield [
                    p.shortid or p.root.split(':')[-1][:6].upper(),
                    p.type or '',
                    p.manufacturer or '',
                    p.model or '',
                    p.cpu_model or '',
                    data.get('cpu_cores', ''),
                    state or '',
                    data.get('ram_total', ''),
                    data.get('ram_type', ''),
                    data.get('ram_slots', ''),
                    data.get('slots_used', ''),
                    data.get('drive', ''),
                    data.get('gpu_model', ''),
                    "".join(user_props.get(p.root, [])),
                    p.serial or '',
                    last_updated or '',
                    str(DeviceBeneficiary.Status(status).label) if status is not None else available,
                ]

    def create_export(self, export_format):
        filename = self._get_filename()

        if export_format == 'csv':
            class EchoBuffer:
                def write(self, value):
                    return value

            def csv_stream():
                writer = csv.writer(EchoBuffer())
                yield writer.writerow(self.HEADERS)
                for row in self._iter_export_rows():
                    yield writer.writerow(row)

            return StreamingHttpResponse(
                csv_stream(),
                content_type='text/csv; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="{filename}.csv"'},
            )

        if export_format == 'xlsx':
            wb = Workbook(write_only=True)
            ws = wb.create_sheet(title="Devices")
            ws.append(self.HEADERS)
            for row in self._iter_export_rows():
                ws.append(row)

            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            return HttpResponse(
                content=buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename="{filename}.xlsx"'},
            )

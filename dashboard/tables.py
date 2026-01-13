import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.dateparse import parse_datetime


class DeviceTable(tables.Table):
    class Meta:
        template_name = "custom_table.html"
        order_by = ("-updated",)
        fields = ('devices', 'shortid',  'type', 'current_state', 'manufacturer', 'model', 'cpu', 'status_beneficiary', 'updated')

    devices = tables.CheckBoxColumn(
        accessor='pk',
        attrs={
            'th__input': {'id': 'select-all', 'class': 'form-check-input'},
            'td__input': {'class': 'select-checkbox form-check-input'},
        },
        orderable=False,
        exclude_from_export=True
    )

    shortid = tables.Column(
        orderable=True,
        linkify=("device:details", {"pk": tables.A("pk")}),
        verbose_name=_("Short ID"),
    )

    current_state = tables.Column(
        accessor='get_current_state.state',
        verbose_name=_("Current State"),
        default="--"
    )

    type = tables.Column(verbose_name=_("Type"), default="")
    manufacturer = tables.Column(verbose_name=_("Manufacturer"), default="")
    model = tables.Column(verbose_name=_("Model"), default="")
    cpu = tables.Column(verbose_name=_("Cpu"), default="")

    status_beneficiary = tables.Column(
        accessor='status_beneficiary',
        verbose_name=_("Status"),
        default=""
    )

    updated = tables.Column(
        accessor="updated",
        verbose_name=("Evidence last updated"),
        attrs={
            'th': {'class': 'text-center text-muted'}
        }
    )

    def render_updated(self, value):
        if isinstance(value, str):
            dt = parse_datetime(value)
            if dt:
                return dt.strftime("%Y-%m-%d %H:%M")
        return value


    def render_type(self, value):
        icons = {
            "Laptop": "bi-laptop", "Netbook": "bi-laptop", "Desktop": "bi-pc-display",
            "Server": "bi-pc-display", "Motherboard": "bi-motherboard", "GraphicCard": "bi-gpu-card",
            "HardDrive": "bi-hdd", "SolidStateDrive": "bi-device-ssd", "NetworkAdapter": "bi-pci-card-network",
            "Processor": "bi-cpu", "RamModule": "bi-memory", "SoundCard": "bi-speaker",
            "Display": "bi-display", "Battery": "bi-battery", "Camera": "bi-camera"
        }
        icon_class = icons.get(value, 'bi-question-circle')
        return format_html('<i class="bi {}"></i> {}', escape(icon_class), escape(value))

import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.utils.html import format_html


class DeviceTable(tables.Table):

    devices = tables.CheckBoxColumn(
        accessor='id',
        attrs={
            'th__input': {
                'id': 'select-all',
                'class': 'form-check-input'
            },
            'td__input': {
                'class': 'select-checkbox form-check-input'
            },
        },
        orderable=False,
        exclude_from_export=True
    )
    shortid = tables.Column(
        linkify=("device:details", {"pk": tables.A("id")}),
        verbose_name=_("Short ID"),
        orderable=True,
    )
    current_state = tables.Column(
        accessor='current_state',
        verbose_name=_("Current State"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-muted text-center'}
        },
        default="N/A"
    )
    type = tables.Column(
        verbose_name=_("Type"),
    )
    manufacturer = tables.Column(
        verbose_name=_("Manufacturer"),
    )
    model = tables.Column(
        verbose_name=_("Model"),
    )
    cpu = tables.Column(
        verbose_name=_("Cpu"),
    )
    status_beneficiary = tables.Column(
        accessor='status_beneficiary',
        verbose_name=_("Status"),
    )
    last_updated = tables.DateTimeColumn(
        format="Y-m-d H:i",
        accessor='last_updated',
        verbose_name=_("Evidence last updated"),
        attrs={
            'th': {
                'class': 'text-center text-muted',
                'data-type': 'date',
                'data-format': 'YYYY-MM-DD HH:mm'
            }
        }
    )
    def render_type(self, value, record):
        icons = {
            "Laptop": "bi-laptop",
            "Netbook": "bi-laptop",
            "Desktop": "bi-pc-display",
            "Server": "bi-pc-display",
            "Motherboard": "bi-motherboard",
            "GraphicCard": "bi-gpu-card",
            "HardDrive": "bi-hdd",
            "SolidStateDrive": "bi-device-ssd",
            "NetworkAdapter": "bi-pci-card-network",
            "Processor": "bi-cpu",
            "RamModule": "bi-memory",
            "SoundCard": "bi-speaker",
            "Display": "bi-display",
            "Battery": "bi-battery",
            "Camera": "bi-camera"
        }

        safe_value = escape(value)
        icon_class = icons.get(value, 'bi-question-circle')

        return format_html(
            '<i class="bi {}"></i> {}',
            escape(icon_class),
            safe_value
        )

    def value_type(self, value, record):

        safe_value = escape(value)
        return format_html(
            safe_value
        )

    def render_model(self, value, record):
        safe_value = escape(value)
        if hasattr(record, 'version') and record.version:
            safe_version = escape(record.version)
            return format_html('{} {}', safe_version, safe_value)
        return safe_value

    class Meta:
        template_name = "custom_table.html"
        order_by = ("-last_updated",)

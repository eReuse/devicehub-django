import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from utils.icons import get_icon_by_type


class DeviceTable(tables.Table):

    devices = tables.CheckBoxColumn(
        accessor='device.id',
        attrs={
            'th__input': {
                'id': 'select-all',
                'class': 'form-check-input'
            },
            'td__input': {
                'class': 'select-checkbox form-check-input'
            },
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
        exclude_from_export=True
    )

    value = tables.Column(
        accessor='value',
        linkify=("device:details", {"pk": tables.A("id")}),
        verbose_name=_("Short ID"),
        orderable=True,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
    )

    current_state = tables.Column(
        accessor='device.current_state',
        verbose_name=_("Current State"),
        orderable=True,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-muted text-center'}
        },
        default="N/A"
    )

    type = tables.Column(
        accessor='device.type',
        verbose_name=_("Type"),
        orderable=False,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )

    manufacturer = tables.Column(
        accessor='device.manufacturer',
        verbose_name=_("Manufacturer"),
        orderable=False,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )

    model = tables.Column(
        accessor='device.model',
        verbose_name=_("Model"),
        orderable=False,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )

    cpu = tables.Column(
        accessor='device.cpu',
        verbose_name=_("Cpu"),
        orderable=False,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )

    status_beneficiary = tables.Column(
        accessor='device.status_beneficiary',
        verbose_name=_("Status"),
        orderable=True,
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )
    created = tables.DateTimeColumn(
        format="Y-m-d H:i",
        accessor='created',
        verbose_name=_("Evidence last updated"),
        orderable=True,
        attrs={
            'td': {'class': 'text-center'},
            'th': {
                'class': 'text-center text-muted',
                'data-type': 'date',
                'data-format': 'YYYY-MM-DD HH:mm'
            }
        }
    )

    def render_type(self, value, record):
        safe_value = escape(value)
        icon_class = get_icon_by_type(value)

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

    def render_value(self, value, record):
        return record.shortid

    class Meta:
        attrs = {
            'class': 'table table-hover table-bordered',
            'thead': {
                'class': 'table-light'
            }
        }
        order_by = ("-created",)

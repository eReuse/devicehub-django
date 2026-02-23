import django_tables2 as tables

from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from utils.icons import get_icon_by_type


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
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
        exclude_from_export=True
    )
    shortid = tables.Column(
        linkify=("device:details", {"pk": tables.A("id")}),
        verbose_name=_("Short ID"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=True,
    )
    current_state = tables.Column(
        accessor='current_state',
        verbose_name=_("Current State"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-muted text-center'}
        },
        default="N/A",
        orderable=True,
    )
    type = tables.Column(
        verbose_name=_("Type"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
    )
    manufacturer = tables.Column(
        verbose_name=_("Manufacturer"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
    )
    model = tables.Column(
        verbose_name=_("Model"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
    )
    cpu = tables.Column(
        verbose_name=_("Cpu"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=False,
    )
    status_beneficiary = tables.Column(
        accessor='status_beneficiary',
        verbose_name=_("Status"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=True,
    )
    last_updated = tables.DateTimeColumn(
        format="Y-m-d H:i",
        accessor='last_updated',
        verbose_name=_("Evidence last updated"),
        attrs={
            'td': {'class': 'text-center'},
            'th': {
                'class': 'text-center text-muted',
                'data-type': 'date',
                'data-format': 'YYYY-MM-DD HH:mm'
            }
        },
        orderable=True,
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

    class Meta:
        template_name = "custom_table.html"
        attrs = {
            'class': 'table table-hover table-bordered',
            'thead': {
                'class': 'table-light'
            }
        }
        order_by = ("-last_updated",)

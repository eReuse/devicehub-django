import django_tables2 as tables
from django_tables2.utils import OrderBy, OrderByTuple

from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from utils.icons import get_icon_by_type


class DeviceTable(tables.Table):

    hide_count = True
    devices = tables.CheckBoxColumn(
        accessor='id',
        attrs={
            'th__input': {
                'class': 'd-none'
            },
            'td__input': {
                'class': 'select-checkbox form-check-input'
            },
            'th': {'class': 'text-center p-0'},
            'td': {'class': 'text-center pe-0'}
        },
        orderable=False,
        exclude_from_export=True
    )
    shortid = tables.Column(
        linkify=("device:details", {"pk": tables.A("link_pk")}),
        verbose_name=_("Short ID"),
        attrs={
            'th': {'class': 'text-center ps-0'},
            'td': {'class': 'text-center ps-0'}
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


class ProductCacheTable(DeviceTable):
    """DeviceTable variant for the projection-backed lists (All Devices,
    Inbox and the lot view). type/manufacturer/model are sorted over the
    ProductCache columns, so their headers are orderable here. The shared
    DeviceTable keeps them non-orderable because the search list orders by
    relevance instead."""

    @property
    def order_by(self):
        return self._order_by

    @order_by.setter
    def order_by(self, value):
        # The view already orders and slices the page (read model + manual
        # sort/pagination). Set the header-arrow indicator WITHOUT re-sorting
        # the data: a re-sort here would override that order using the
        # displayed strings -- e.g. floating the '--' no-state placeholder
        # above real states (since '-' sorts before letters) and ordering
        # status_beneficiary by its label instead of its enum value. This
        # mirrors the base setter but drops the final ``self.data.order_by``.
        order_by = () if not value else value
        order_by = order_by.split(",") if isinstance(order_by, str) else order_by
        valid = [
            alias for alias in order_by
            if OrderBy(alias).bare in self.columns
            and self.columns[OrderBy(alias).bare].orderable
        ]
        self._order_by = OrderByTuple(valid)

    type = tables.Column(
        verbose_name=_("Type"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=True,
    )
    manufacturer = tables.Column(
        verbose_name=_("Manufacturer"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=True,
    )
    model = tables.Column(
        verbose_name=_("Model"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        },
        orderable=True,
    )

    class Meta(DeviceTable.Meta):
        # Inherit template_name (custom_table.html), attrs and default order_by;
        # without this django-tables2 falls back to its own template, changing
        # the header and dropping the custom pagination.
        pass


class AllDevicesTable(ProductCacheTable):
    """ProductCacheTable for the All Devices / Inbox lists. current_state
    is not orderable here: it is not a ProductCache column, so it cannot be
    ordered at the DB level (see ProductCacheTableMixin.SORTABLE_FIELDS), and
    these lists are paginated in the database to avoid materialising every
    device. Without a header arrow there is no misleading control that does not
    actually sort. The lot view keeps it orderable, sorting in Python."""

    current_state = tables.Column(
        accessor='current_state',
        verbose_name=_("Current State"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-muted text-center'}
        },
        default="N/A",
        orderable=False,
    )

    class Meta(ProductCacheTable.Meta):
        pass

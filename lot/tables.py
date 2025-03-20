import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from lot.models import Lot
from django.utils.safestring import mark_safe

class LotTable(tables.Table):
    select = tables.CheckBoxColumn(
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
        orderable=False
    )
    name = tables.Column(
        linkify=("dashboard:lot", {"pk": tables.A("id")}),
        verbose_name=_("Lot Name"),
        attrs={
            'th': {'class': 'text-start'},
            'td': {'class': 'fw-bold text-start'}
        }
    )
    description = tables.Column(
        verbose_name=_("Description"),
        default=_("No description"),
        attrs={
            'th': {'class': 'text-start'},
            'td': {'class': 'text-muted text-start'}
        }
    )
    archived = tables.Column(
        verbose_name=_("Status"),
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )
    device_count = tables.Column(
        verbose_name=_("Devices"),
        accessor='device_count',
        attrs={
            'th': {'class': 'text-center'},
            'td': {'class': 'text-center'}
        }
    )
    created = tables.DateColumn(
        format="Y-m-d",
        verbose_name=_("Created On"),
        attrs={
            'th': {'class': 'text-end'},
            'td': {'class': 'text-end'}
        }
    )
    user = tables.Column(
        verbose_name=_("Created By"),
        default=_("Unknown"),
        attrs={
            'th': {'class': 'text-end'},
            'td': {'class': 'text-muted text-end'}
        }
    )
    actions = tables.TemplateColumn(
        template_name="lot_actions.html",
        verbose_name=_(""),
        attrs={
            'th': {'class': 'text-end'},
            'td': {'class': 'text-end'}
        }
    )

    def render_archived(self, value):
        if value:
            return mark_safe('<span class="badge bg-warning"><i class="bi bi-archive-fill"></i></span>')
        return mark_safe('<span class="badge bg-success"><i class="bi bi-folder-fill"></i></span>')

    class Meta:
        model = Lot
        fields = ("select", "archived", "name", "description", "device_count", "created", "user", "actions")
        attrs = {
            "class": "table table-hover align-middle",
            "thead": {"class": "table-light"}
        }
        order_by = ("-created",)

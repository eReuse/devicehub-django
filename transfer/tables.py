import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from transfer.models import Transfer
from django.utils.safestring import mark_safe

class TransferTable(tables.Table):
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
        },
        orderable=False
    )
    name = tables.Column(
        linkify=("dashboard:transfer", {"pk": tables.A("id")}),
        verbose_name=_("Transfer Name"),
        attrs={
        }
    )
    description = tables.Column(
        verbose_name=_("Description"),
        default=_("No description"),
        attrs={
            'td': {'class': 'text-muted'}
        }
    )
    archived = tables.Column(
        verbose_name=_("Status"),
    )
    device_count = tables.Column(
        verbose_name=_("Devices"),
        accessor='device_count',
    )
    created = tables.DateColumn(
        format="Y-m-d",
        verbose_name=_("Created On"),
    )
    user = tables.Column(
        verbose_name=_("Created By"),
        default=_("Unknown"),
    )
    actions = tables.TemplateColumn(
        template_name="transfer_actions.html",
        verbose_name=_(""),
    )

    def render_archived(self, value):
        if value:
            return mark_safe('<span class="badge bg-warning"><i class="bi bi-archive-fill"></i></span>')
        return mark_safe('<span class="badge bg-success"><i class="bi bi-folder-fill"></i></span>')

    class Meta:
        template_name = "custom_table.html"
        model = Transfer
        fields = ("select", "archived", "name", "description", "device_count", "created", "user", "actions")
        order_by = ("-created",)

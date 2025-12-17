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
    organization_name = tables.Column(
        verbose_name=_("Organization Name"),
    )
    credential_id = tables.Column(
        linkify=("transfer:id", {"id": tables.A("id")}),
        verbose_name=_("Credential Id"),
        attrs={
        }
    )
    lot = tables.Column(
       linkify=("dashboard:lot", {"pk": tables.A("get_id_lot")}),
       verbose_name=_("Lot"),
    )
    created = tables.DateColumn(
        format="Y-m-d",
        verbose_name=_("Created On"),
    )

    class Meta:
        template_name = "custom_table.html"
        model = Transfer
        fields = (
            "select",
            "credential_id",
            "organization_name",
            "number_items",
            "lot",
            "created"
        )
        order_by = ("-created",)


class DeviceTable(tables.Table):
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

    shortid = tables.Column(
        linkify=("transfer:device", {"id": tables.A("transfer"), "pk": tables.A("id")}),
        verbose_name=_("Short id"),
        attrs={
        }
    )

    name = tables.Column(
    )

    class Meta:
        template_name = "custom_table.html"
        model = Transfer
        fields = (
            "select",
            "shortid",
            "name"
        )
        order_by = ("-name",)

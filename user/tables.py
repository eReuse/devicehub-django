import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from lot.models import Lot
from action.models import StateDefinition

from api.models import Token


class ButtonColumn(tables.Column):
    attrs = {
        "a": {
            "type": "button",
            "class": "text-danger",
            "title": "Remove",
        }
    }
    # it makes no sense to order a column of buttons
    orderable = False
    # django_tables will only call the render function if it doesn't find
    # any empty values in the data, so we stop it from matching the data
    # to any value considered empty
    empty_values = ()

    def render(self):
        return format_html('<i class="bi bi-trash"></i>')


class TokensTable(tables.Table):
    delete = ButtonColumn(
            verbose_name=_("Delete"),
            linkify={
                "viewname": "api:delete_token",
                "args": [tables.A("pk")]
            },
            orderable=False
    )
    edit_token = ButtonColumn(
            linkify={
                "viewname": "api:edit_token",
                "args": [tables.A("pk")]
                },
            attrs = {
                "a": {
                    "type": "button",
                    "class": "text-primary",
                    "title": "Remove",
                }
            },
            orderable=False,
            verbose_name="Edit"
            )
    token = tables.Column(verbose_name=_("Token"), empty_values=())
    tag = tables.Column(verbose_name=_("Tag"), empty_values=())

    def render_view_user(self):
        return format_html('<i class="bi bi-eye"></i>')

    def render_edit_token(self):
        return format_html('<i class="bi bi-pencil-square"></i>')

    # def render_token(self, record):
    #     return record.get_memberships()

    # def order_membership(self, queryset, is_descending):
    #     # TODO: Test that this doesn't return more rows than it should
    #     queryset = queryset.order_by(
    #         ("-" if is_descending else "") + "memberships__type"
    #     )

    #     return (queryset, True)

    # def render_role(self, record):
    #     return record.get_roles()

    # def order_role(self, queryset, is_descending):
    #     queryset = queryset.order_by(
    #         ("-" if is_descending else "") + "roles"
    #     )

    #     return (queryset, True)

    class Meta:
        model = Token
        template_name = "custom_table.html"
        fields = ("tag", "token",  "edit_token")
        sequence = ("tag", "token",  "edit_token")

class LotSelectionTable(tables.Table):
    # Declare columns for ordering, but 'select' will be overridden
    select = tables.CheckBoxColumn(accessor="pk")
    name = tables.Column(verbose_name=_("Lot Name"))

    def __init__(self, *args, checked_pks=None, **kwargs):
        if checked_pks is None:
            checked_pks = set()

        # Re-declare the 'select' column, passing checked_pks to its constructor
        extra_columns = [
            ("select", tables.CheckBoxColumn(
                accessor="pk",
                checked_pks=checked_pks,  # <-- Pass it to the constructor
                attrs={"th__input": {"onclick": "toggle(this)"}}
            ))
        ]

        # Pass them to super() using the extra_columns kwarg
        kwargs["extra_columns"] = extra_columns
        super().__init__(*args, **kwargs)

        # We must explicitly set the column order now
        self.sequence = ("select", "name")

    class Meta:
        model = Lot
        fields = ("select", "name")
        # Ensure your custom template correctly renders column attributes
        template_name = "custom_table.html"
        row_attrs = {"data-id": lambda record: record.pk}


class LotSelectionTable(tables.Table):
    select = tables.CheckBoxColumn(
        accessor="pk",
        attrs={"th__input": {"onclick": "toggle(this)"}}
    )
    name = tables.Column(verbose_name=_("Lot Name"))

    def render_select(self, record):
        is_checked = record.pk in getattr(self, "checked_pks", set())
        checked_attr = "checked" if is_checked else ""

        return format_html(
            '<input type="checkbox" name="select_lot" value="{}" class="form-check-input" {}>',
            record.pk,
            checked_attr
        )

    class Meta:
        model = Lot
        fields = ("select", "name")
        template_name = "custom_table.html"
        row_attrs = {"data-id": lambda record: record.pk}


class StateSelectionTable(tables.Table):
    select = tables.CheckBoxColumn(
        accessor="pk",
        attrs={"th__input": {"onclick": "toggle(this)"}}
    )
    state = tables.Column(verbose_name=_("State Name"), accessor="state")

    def render_select(self, record):
        is_checked = record.pk in getattr(self, "checked_pks", set())
        checked_attr = "checked" if is_checked else ""

        return format_html(
            '<input type="checkbox" name="select_state" value="{}" class="form-check-input" {}>',
            record.pk,
            checked_attr
        )

    class Meta:
        model = StateDefinition
        fields = ("select", "state")
        template_name = "custom_table.html"
        row_attrs = {"data-id": lambda record: record.pk}

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

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
                "viewname": "user:delete_token",
                "args": [tables.A("pk")]
            },
            orderable=False
    )
    edit_token = ButtonColumn(
            linkify={
                "viewname": "user:edit_token",
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
    qr = tables.Column(verbose_name=_("QR"), empty_values=(), orderable=False)
    token = tables.Column(verbose_name=_("Token"), empty_values=())
    tag = tables.Column(verbose_name=_("Tag"), empty_values=())

    def render_view_user(self):
        return format_html('<i class="bi bi-eye"></i>')

    def render_edit_token(self):
        return format_html('<i class="bi bi-pencil-square"></i>')

    def render_qr(self, record):
        """Button only: the QR carries the token, so it stays hidden until
        the user asks for it (token.html loads the image on click)."""
        return format_html(
            '<button type="button" class="btn btn-sm btn-outline-secondary js-token-qr"'
            ' data-qr-url="{}" data-tag="{}" title="{}">'
            '<i class="bi bi-qr-code"></i> {}</button>',
            reverse("user:token_qr", args=[record.pk]),
            record.tag or "",
            _("Show the token as a QR code"),
            _("Show QR"),
        )

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
        template_name = "custom_table.html"
        model = Token
        fields = ("token", "tag", "is_active" , "edit_token")

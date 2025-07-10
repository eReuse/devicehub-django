import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from api.models import Token


class TokensTable(tables.Table):
    token = tables.Column(
        verbose_name=_("Token"),
        attrs={
            "td": {"class": "align-middle ps-3"},
            "th": {"class": "ps-3"}
        }
    )

    tag = tables.Column(
        verbose_name=_("Tag"),
        attrs={"td": {"class": "align-middle"}}
    )

    actions = tables.Column(
        verbose_name=_(""),
        orderable=False,
        empty_values=(),
        attrs={
            "td": {"class": "text-end pe-3", "width": "150px"},
            "th": {"class": "text-end pe-3"}
        }
    )

    class Meta:
        model = Token
        template_name = "custom_table.html"
        fields = ("token", "tag", "actions")
        attrs = {
            "class": "table table-hover align-middle",
            "thead": {"class": "table-light"}
        }
        row_attrs = {"class": "py-2"}
        empty_text = format_html(
            '<div class="p-4 text-muted text-center">{}</div>',
            _("No tokens found")
        )

    def render_token(self, value, record):
        return format_html(
            '''
            <div class="d-flex align-items-center">
                <a href="{}" class="font-monospace text-decoration-none me-2"
                   title="{}">
                   {}
                </a>
                <button class="btn btn-sm btn-link text-muted p-0 copy-clipboard"
                        data-token="{}" title="{}">
                    <i class="bi bi-clipboard"></i>
                </button>
            </div>
            ''',
            reverse("api:edit_token", args=[record.pk]),
            _("Edit token"),
            value,
            value,
            _("Copy to clipboard")
        )

    def render_tag(self, value):
        if not value:
            return format_html('<span class="text-muted">{}</span>', _("No tag"))
        return format_html('<span class="badge badge-lg bg-light text-dark">{}</span>', value)

    def render_actions(self, record):
        return format_html(
            '''
            <div class="btn-group btn-group-sm">
                <a href="{}" class="btn btn-outline-danger" title="{}">
                    {}
                    <i class="bi bi-trash"></i>
                </a>
            </div>
            ''',
            _("Delete"),
            reverse("api:delete_token", args=[record.pk]),
            _("Delete")
        )

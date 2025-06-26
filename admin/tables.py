# tables.py
import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

from user.models import User

class UserTable(tables.Table):


    id = tables.Column(
        verbose_name=_("User ID"),
        attrs={
            'th': {
                'style': 'width:8%',
            },
        },
    )

    status = tables.Column(
        verbose_name=_("Status"),
        orderable=True,
        accessor="is_admin",
        attrs={
            'th': {
                'style': 'width:12%',
            },
        },
    )
    email = tables.Column(verbose_name=_("Email address"))

    last_login = tables.DateTimeColumn(
        format="Y-m-d H:i",
        verbose_name=_("Last Login"),
        attrs={
            'th': {
                'data-type': 'date',
                'data-format': 'YYYY-MM-DD HH:mm'
            },
        },
    )

    class Meta:
        model = User
        fields = ()
        attrs = {
            'class': 'table table-hover table-bordered',
            'thead': {
                'class': 'table-light text-center'
            },
            'tbody': {
                'class': 'text-center'
            }
        }
        orderable = True
        empty_text = _("No user records found")

    def render_email(self, value, record):
        try:
            url = reverse('user:profile', kwargs={'pk': record.pk})
            return format_html(
                '<a href="{}" class="text-decoration-none link-primary">{}</a>',
                url, value
            )
        except Exception:
            return self.render_error_message(_("Error loading email"))

    def render_status(self, record):
        try:
            elements = []

            admin_class = 'bg-success' if record.is_admin else 'bg-secondary'
            admin_text = _("Admin") if record.is_admin else _("User")
            elements.append(format_html('<span class="badge {}">{}</span>', admin_class, admin_text))

            if not record.is_active:
                elements.append(format_html(
                    '<span class="badge bg-secondary me-1">{}</span>',
                    _("Inactive")
                ))

            # if hasattr(record, 'accept_gdpr') and not record.accept_gdpr:
            #     elements.append(format_html(
            #         '<span class="badge bg-warning text-dark">{}</span>',
            #         _("GDPR Pending")
            #     ))

            return format_html(' '.join(elements)) if elements else self.render_empty(_("N/A"))
        except Exception:
            return self.render_error_message(_("Error checking status"))

    def render_empty(self, message=_("Unknown")):
        return format_html(
            '<span class="text-muted">{}</span>',
            message
        )

    def render_error_message(self, message=_("An error occurred")):
        return format_html(
            '<span class="text-danger" title="{}"><i class="bi bi-exclamation-circle-fill me-1"></i>{}</span>',
            message,
            _("Error")
        )

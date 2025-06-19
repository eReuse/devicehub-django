#!/usr/bin/env python3
import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from evidence.models import Evidence
import logging


logger = logging.getLogger('django')

class EvidenceTable(tables.Table):
    uuid = tables.Column(verbose_name=_("UUID"),
        attrs={
            'th': {'class': 'text-start'},
            'td': {'class': 'font-monospace text-start'}
        },
        orderable=False
    )

    created = tables.DateTimeColumn(
        format="Y-m-d H:i",
        verbose_name=_("Upload Date"),
        attrs={
            'th': {
                'data-type': 'date',
                'data-format': 'YYYY-MM-DD HH:mm'
            },
        },
        orderable=True
    )

    uploaded_by = tables.Column(verbose_name=_("Uploaded by"),
        accessor='user',
        orderable=True
    )

    did_document = tables.Column(verbose_name=_("DID Document"), accessor="uuid")
    legacy = tables.Column(verbose_name=_("Legacy"), accessor="uuid")
    ev_type = tables.Column(verbose_name=_("Type"), accessor="uuid")
    device = tables.Column(verbose_name=_("Device"), accessor="value")

    class Meta:
        attrs = {
            'class': 'table table-hover table-bordered',
            'thead': {
                'class': 'table-light text-center'
            },
            'tbody': {
                'class': 'text-center'
            }
        }
        orderable= False
        order_by = ("-created")
        sequence = ('device','uuid','did_document', 'legacy', 'ev_type', 'uploaded_by', 'created')

        @property
        def empty_text(self):
            return format_html(
                '<div class="text-muted text-center">{}</div>',
                _("No evidence records found")
            )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence_map = {}

    def before_render(self, request):
        if self.page:
            if hasattr(self.page.object_list, 'data'):
                paginated_ids = [item.uuid for item in self.page.object_list.data]
                # Lazy instantiate paginated devices by uuid and map them for did document
                self.evidence_map = {
                    uuid: Evidence(uuid)
                    for uuid in paginated_ids
                }
            else:
                self.evidence_map = {}

    def render_device(self, value):
        try:
            url = reverse('device:details', kwargs={'pk': value })
            return format_html(
                '<a href="{}" class="text-decoration-none link-primary">{}</a>',
                url,
                value[:7].upper()
            )
        except Exception:
            return self.render_error_message(_("Error loading device"))


    def render_uuid(self, value):
        try:
            url = reverse('evidence:details', kwargs={'pk': value})
            return format_html(
                '''<a href="{}" class="font-monospace text-decoration-none"
                    title="{}">
                   <i class="bi bi-file-earmark-text"></i>{}
                   </a>''',
                url,
                value,
                value
            )
        except Exception:
            return self.render_error_message(_("Error loading UUID"))


    def render_uploaded_by(self, value, record):
        try:
            if not hasattr(record, 'user') or not record.user:
                return self.render_empty(_("System"))

            url = reverse('user:profile', kwargs={'pk': record.user.pk})
            return format_html(
                '<a href="{}" class="text-decoration-none link-primary">{}</a>',
                url,
                record.user.email
            )
        except Exception:
            return self.render_error_message(_("Error loading uploader"))

    def render_did_document(self, value):
        try:
            ev = self.evidence_map.get(value)
            if not ev:
                return self.render_empty(_("N/A (Evidence not found)"))

            did_url = ev.did_document()
            if not did_url:
                return self.render_empty(_("Not available"))

            return format_html(
                '''<a href="{}" class="text-decoration-none"
                    target="_blank" rel="noopener noreferrer"
                    title="View DID Document">
                <i class="bi bi-file-earmark-lock me-2"></i>{}
                </a>''',
                did_url, # The URL should be the first argument
                _("DID document")
            )
        except Exception as e:
            # Log the exception for debugging if necessary
            # logger.error(f"Error rendering DID document for {value}: {e}")
            return self.render_error_message(_("Error rendering DID"))

    def render_legacy(self, record, value):
        try:
            ev = self.evidence_map.get(value)
            if not ev:
                return self.render_empty()

            is_legacy = ev.is_legacy()

            return format_html(
                '<span class="{}">{}</span>',
                "fw-bold" if is_legacy else "fst-italic",
                _("Legacy") if is_legacy else _("Modern")
            )
        except Exception:
            return self.render_error_message(_("Error checking legacy status"))

    def render_ev_type(self, value):
        try:
            ev = self.evidence_map.get(value)
            if not ev:
                return self.render_empty()
            return ev.get_chassis() if hasattr(ev, 'get_chassis') else self.render_empty(_("N/A (Type not found)"))
        except Exception:
            return self.render_error_message(_("Error rendering evidence type"))

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

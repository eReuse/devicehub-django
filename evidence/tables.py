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
    #always pass uuid
    uuid = tables.Column(verbose_name=_("Evidence UUID"), accessor='0')
    time = tables.Column(verbose_name=_("Upload Date"), accessor='1')
    uploaded_by = tables.Column(verbose_name=_("Uploaded By"), accessor='0')
    did_document = tables.Column(verbose_name=_("DID document"), accessor='0')
    legacy = tables.Column(verbose_name=_("Legacy"), accessor='0')


    class Meta:
        attrs = {
            'class': 'table table-hover align-middle',
            'thead': {
                'class': 'table-light'
            }
        }
        orderable = False
        sequence = ('uuid', 'time', 'uploaded_by')

        @property
        def empty_text(self):
            return format_html(
                '<div class="p-4 text-muted text-center">{}</div>',
                _("No evidence records found")
            )

    def before_render(self, request):
        if self.page:
            paginated_ids = [item[0] for item in self.page.object_list.data]
            #lazy instantiate paginated devices by uuid and map them for did document
            self.data = {
                str(uuid): Evidence(uuid)
                for uuid in paginated_ids
            }

    def render_uuid(self, value):
        url = reverse('evidence:details', kwargs={'pk': value})
        return format_html(
            '''<a href="{}" class="d-block font-monospace text-decoration-none"
                title="{}">
               <i class="bi bi-file-earmark-text me-2"></i>{}
               </a>''',
            url,
            value,
            value
        )

    def render_time(self, value):
        if timezone.is_naive(value):
            if hasattr(settings, 'TIME_ZONE'):
                value = timezone.make_aware(value, timezone.get_default_timezone())
            else:
                return value.strftime("%Y-%m-%d %H:%M")

        local_time = timezone.localtime(value)
        return format_html(
            '''<div class="d-flex flex-column">
               <span class="fw-medium">{}</span>
               <small class="text-muted">{}</small>
               </div>''',
            local_time.strftime("%b %d, %Y"),
            local_time.strftime("%H:%M")
        )

    def render_uploaded_by(self, value):
        ev = self.data.get(str(value))

        if not ev:
            return _("System")
        return format_html(
            '<p class="text-muted">{}</p>',
            str(ev.uploaded_by)
        )

    def render_did_document(self, value):
        ev = self.data.get(str(value))
        if not ev:
            return format_html('<span class="text-muted">{}</span>', _("Unknown"))

        did_url = ev.did_document()
        if not did_url:
            return format_html('<span class="text-muted">{}</span>', _("Not available"))

        return format_html(
            '''<a href="{}" class="d-block text-decoration-none"
                target="_blank" rel="noopener noreferrer"
                title="View DID Document">
            <i class="bi bi-file-earmark-lock me-2"></i>DID Document
            </a>''',
            did_url
        )

    def render_legacy(self, record, value):
        ev = self.data.get(str(value))
        if not ev:
            return format_html('<span class="text-muted">{}</span>', _("Unknown"))

        is_legacy = ev.inxi is None
        return format_html(
            '''
            <span class="" title="{}">
                {}
            </span>
            ''',
            _("Legacy") if is_legacy else _("Modern"),
            _("Legacy") if is_legacy else _("Modern")
        )

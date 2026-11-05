#!/usr/bin/env python3
import logging
from django.core.management.base import BaseCommand
from action.models import StateDefinition
from user.models import Institution
from django.utils.translation import gettext as _

logger = logging.getLogger('django')


class Command(BaseCommand):
    help = 'Create default StateDefinitions for a given institution.'

    def add_arguments(self, parser):
        parser.add_argument('institution_name', type=str, help='The name of the institution')

    def handle(self, *args, **kwargs):
        # DONATION and DISMANTLE carry a DTE config so the environmental impact
        # recognises them whatever their (translated) name: a transfer starts a
        # device's second life, a recycled disposition ends it.
        default_states = [
            {
                "state": _("INBOX"),
                "description": _("Initial state for newly received or registered devices.")
            },
            {
                "state": _("VISUAL INSPECTION"),
                "description": _("Physical assessment and cosmetic grading of the device.")
            },
            {
                "state": _("REPAIR"),
                "description": _("Device is undergoing hardware repairs or component replacements.")
            },
            {
                "state": _("INSTALL"),
                "description": _("Operating system and required software are being installed.")
            },
            {
                "state": _("TEST"),
                "description": _("Quality assurance, stress testing, and functional verification.")
            },
            {
                "state": _("PACKAGING"),
                "description": _("Device is cleaned, boxed, and prepared for final delivery.")
            },
            {
                "state": _("DONATION"),
                "description": _("Device has been successfully delivered or donated to a beneficiary."),
                "dte_config": {"event_type": "MoveEvent", "disposition": "active"},
            },
            {
                "state": _("DISMANTLE"),
                "description": _("Device is being disassembled for spare parts or e-waste recycling."),
                "dte_config": {"disposition": "recycled"},
            },
        ]

        institution_name = kwargs['institution_name']
        institution = Institution.objects.filter(name=institution_name).first()

        if not institution:
            txt = "No institution found for: %s. Please create an institution first"
            logger.error(txt, institution_name)
            self.stdout.write(self.style.ERROR(txt % institution_name))
            return

        for item in default_states:
            state_def, created = StateDefinition.objects.get_or_create(
                institution=institution,
                state=item["state"],
                defaults={
                    'description': item["description"],
                    'dte_config': item.get("dte_config", {}),
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created state: {item["state"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'State already exists: {item["state"]}'))

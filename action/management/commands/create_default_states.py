#!/usr/bin/env python3
import logging
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from action.models import StateDefinition, Institution

logger = logging.getLogger('django')


# Opt-in workflow states, appended after the institution's existing ones,
# as (name, description).
# INITIAL_STATE is not here: add_institution (and the data migration for
# older institutions) already creates it. State names are user-defined
# data, so they are not translated.
DEFAULT_STATES = [
    ("VISUAL INSPECTION", _("Physical assessment and cosmetic grading of the device.")),
    ("REPAIR", _("Device is undergoing hardware repairs or component replacements.")),
    ("INSTALL", _("Operating system and required software are being installed.")),
    ("TEST", _("Quality assurance, stress testing, and functional verification.")),
    ("PACKAGING", _("Device is cleaned, boxed, and prepared for final delivery.")),
    ("DONATION", _("Device has been successfully delivered or donated to a beneficiary.")),
    ("DISMANTLE", _("Device is being disassembled for spare parts or e-waste recycling.")),
]


class Command(BaseCommand):
    help = 'Add the default StateDefinitions to a given institution.'

    def add_arguments(self, parser):
        parser.add_argument('institution_name', type=str, help='The name of the institution')

    def handle(self, *args, **kwargs):
        institution_name = kwargs['institution_name']
        institution = Institution.objects.filter(name=institution_name).first()

        if not institution:
            txt = "No institution found for: %s. Please create an institution first"
            logger.error(txt, institution_name)
            self.stdout.write(self.style.ERROR(txt % institution_name))
            return

        for state, description in DEFAULT_STATES:
            created = StateDefinition.objects.get_or_create(
                institution=institution,
                state=state,
                defaults={'description': description},
            )[1]
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created state: {state}'))
            else:
                self.stdout.write(self.style.WARNING(f'State already exists: {state}'))

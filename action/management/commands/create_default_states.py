#!/usr/bin/env python3
import logging
from django.core.management.base import BaseCommand
from action.models import StateDefinition, Institution
from django.utils.translation import gettext as _

logger = logging.getLogger('django')

class Command(BaseCommand):
    help = 'Create default StateDefinitions for a given institution. "'

    def add_arguments(self, parser):
        parser.add_argument('institution_name', type=str, help='The name of the institution')

    def handle(self, *args, **kwargs):
        default_states = [
            _("INBOX"),
            _("VISUAL INSPECTION"),
            _("REPAIR"),
            _("INSTALL"),
            _("TEST"),
            _("PACKAGING"),         
            _("DONATION"),
            _("DISMANTLE")
        ]

        institution_name = kwargs['institution_name']
        institution = Institution.objects.filter(name=institution_name).first()

        if not institution:
            txt = "No institution found for: %s. Please create an institution first"
            logger.error(txt, institution.name)
            return

        for state in default_states:
            state_def, created = StateDefinition.objects.get_or_create(
                institution=institution,
                state=state
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created state: {state}'))
            else:
                self.stdout.write(self.style.WARNING(f'State already exists: {state}'))

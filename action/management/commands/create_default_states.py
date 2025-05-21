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
        parser.add_argument(
            '--language', '-l',
            default='en',
            type=str,
            choices={"en","es","ca"},
            help='Language code for initial states (es/en/ca).',
        )

    def handle(self, *args, **kwargs):
        default_states = [
            "INBOX",
            "VISUAL INSPECTION",
            "REPAIR",
            "INSTALL",
            "TEST",
            "PACKAGING",
            "DONATION",
            "DISMANTLE"
        ]

        institution_name = kwargs['institution_name']
        institution = Institution.objects.filter(name=institution_name).first()

        if not institution:
            txt = "No institution found for: %s. Please create an institution first"
            logger.error(txt, institution.name)
            return

        lang_code = kwargs['language']
        match lang_code:
            case "en":
                pass
            case "es":
                default_states = [
                    "ENTRADA",
                    "INSPECCION VISUAL",
                    "REPARACIÓN",
                    "INSTALADO",
                    "PRUEBAS",
                    "EMPAQUETADO",
                    "DONACION",
                    "DESMANTELADO"
                ]
            case "ca":
                default_states = [
                    "ENTRADA",
                    "INSPECCIÓ VISUAL",
                    "REPARACIÓ",
                    "INSTAL·LAT",
                    "PROVES",
                    "EMPAQUETAT",
                    "DONACIÓ",
                    "DESMANTELLAT"
                    ]
            case _:
                logger.error("Language not supported %s. Fallback to english", lang_code)

        for state in default_states:
            state_def, created = StateDefinition.objects.get_or_create(
                institution=institution,
                state=state
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created state: {state}'))
            else:
                self.stdout.write(self.style.WARNING(f'State already exists: {state}'))

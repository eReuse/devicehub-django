from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _
from user.models import Institution
from lot.models import LotTag, Lot


class Command(BaseCommand):
    help = "Create a new Institution"

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help=_('Institution name'))
        parser.add_argument(
            '--language', '-l',
            default='en',
            type=str,
            choices={'en', 'es', 'ca'},
            help=_('Language code for default tags (en/es/ca)'),
        )
        parser.add_argument(
            '--demo', '-d',
            action='store_true',
            default=False,
            help=_('Load initial demo lots'),
        )

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.create(name=kwargs['name'])
        lang_code = kwargs['language']
        self.create_lot_tags(lang_code)

        if kwargs['demo']:
            self.create_lots()

    def create_lot_tags(self, lang_code):
        _tags = {
            'en': {
                'inbox': "Inbox",
                'others': ["Admission", "Departure", "Temporary"]
            },
            'es': {
                'inbox': "Lote de entrada",
                'others': ["Entrada", "Salida", "Temporal"]
            },
            'ca': {
                'inbox': "Safata d'entrada",
                'others': ["Entrada", "Sortida", "Temporal"]
            }
        }
        LotTag.objects.create(
            inbox=True,
            name=_tags[lang_code]['inbox'],
            owner=self.institution
        )
        for tag_name in _tags[lang_code]['others']:
            LotTag.objects.create(
                name=tag_name,
                owner=self.institution
            )

    def create_lots(self):
        for g in LotTag.objects.all():
            #If more languages are supported, then this logic should be changed
            if g.name in { "Entrada", "Admission"}:
                Lot.objects.create(
                    name="donante-orgA",
                    owner=self.institution,
                    archived=True,
                    type=g
                )
                Lot.objects.create(
                    name="donante-orgB",
                    owner=self.institution,
                    type=g
                )
                Lot.objects.create(
                    name="donante-orgC",
                    owner=self.institution,
                    type=g
                )

            if g.name in {"Salida", "Departure", "Sortida"}:
                Lot.objects.create(
                    name="beneficiario-org1",
                    owner=self.institution,
                    type=g
                )
                Lot.objects.create(
                    name="beneficiario-org2",
                    owner=self.institution,
                    archived=True,
                    type=g
                )
                Lot.objects.create(
                    name="beneficiario-org3",
                    owner=self.institution,
                    type=g
                )

            if g.name in {"Temporal", "Temporary"}:
                Lot.objects.create(
                    name="palet1",
                    owner=self.institution,
                    type=g
                )
                Lot.objects.create(
                    name="palet2",
                    owner=self.institution,
                    type=g
                )
                Lot.objects.create(
                    name="palet3",
                    owner=self.institution,
                    archived=True,
                    type=g
                )

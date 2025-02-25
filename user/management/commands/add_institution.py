from django.core.management.base import BaseCommand
from user.models import Institution
from lot.models import LotTag, Lot


class Command(BaseCommand):
    help = "Create a new Institution"

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='institution')

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.create(name=kwargs['name'])
        self.create_lot_tags()
        self.create_lots()

    def create_lot_tags(self):
        LotTag.objects.create(
            inbox=True,
            name="Inbox",
            owner=self.institution
        )
        tags = [
            "Entrada",
            "Salida",
            "Temporal"
        ]
        for tag in tags:
            LotTag.objects.create(
                name=tag,
                owner=self.institution
            )

    def create_lots(self):
        for g in LotTag.objects.all():
            if g.name == "Entrada":
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

            if g.name == "Salida":
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

            if g.name == "Temporal":
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

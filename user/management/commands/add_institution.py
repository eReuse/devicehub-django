from django.core.management.base import BaseCommand
from django.conf import settings

from user.models import Institution
from lot.models import LotTag, Lot
from device.models import DeviceType, DeviceTypeAttribute, DEFAULT_PRODUCT_TYPES


class Command(BaseCommand):
    help = "Create a new Institution"

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='institution')

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.create(name=kwargs['name'])
        # create lot groups "Entrada, Temporal, Salida" (TODO in English?)
        self.create_lot_tags()
        self.create_product_types()
        if settings.DEMO:
            self.create_demo_lots()

    def create_product_types(self):
        for name, attribute_names in DEFAULT_PRODUCT_TYPES.items():
            device_type = DeviceType.objects.create(
                name=name,
                institution=self.institution
            )
            DeviceTypeAttribute.objects.bulk_create([
                DeviceTypeAttribute(
                    device_type=device_type,
                    name=attribute_name,
                    order=order
                )
                for order, attribute_name in enumerate(attribute_names, start=1)
            ])

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

    def create_demo_lots(self):
        for g in LotTag.objects.filter(owner=self.institution):
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

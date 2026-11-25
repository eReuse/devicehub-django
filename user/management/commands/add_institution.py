from django.core.management.base import BaseCommand

from user.models import Institution
from lot.models import LotTag
from device.models import DeviceType, DeviceTypeAttribute, DEFAULT_PRODUCT_TYPES
from action.models import StateDefinition, INITIAL_STATE


class Command(BaseCommand):
    help = "Create a new Institution"

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='institution')

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.create(name=kwargs['name'])
        # create lot groups "Entrada, Temporal, Salida" (TODO in English?)
        self.create_lot_tags()
        self.create_product_types()
        self.create_initial_state()

    def create_initial_state(self):
        # Every institution needs at least one state so new devices can be
        # assigned to it; the full default set is opt-in (create_default_states).
        StateDefinition.objects.create(
            institution=self.institution,
            state=INITIAL_STATE
        )

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

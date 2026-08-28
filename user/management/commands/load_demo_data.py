from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from device.models import Device
from user.models import Institution
from lot.models import LotTag, Lot, LotSubscription, Beneficiary


User = get_user_model()

# lot name -> archived, grouped by lot tag
DEMO_LOTS = {
    "Entrada": [
        ("donante-orgA", True),
        ("donante-orgB", False),
        ("donante-orgC", False),
    ],
    "Salida": [
        ("beneficiario-org1", False),
        ("beneficiario-org2", True),
        ("beneficiario-org3", False),
        ("beneficiario-org4", False),
    ],
    "Temporal": [
        ("palet1", False),
        ("palet2", False),
        ("palet3", True),
    ],
}

B2C_LOT = "beneficiario-org4"
B2C_SHOP = "shop@example.org"
B2C_DEVICES = 25
B2C_BENEFICIARIES = [f"beneficiary{i}@example.org" for i in range(1, 5)]


class Command(BaseCommand):
    help = "Create user for test"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.first()
        self.password = "1234"
        users = [
            "donor@example.org",
            "circuit-manager@example.org",
            "shop@example.org",
            "beneficiary@example.org",
        ]

        for email in users:
            self.create_user(email)

        self.create_demo_lots()
        self.create_demo_b2c()

    def create_user(self, email):
        User.objects.create_user(
            institution=self.institution,
            email=email,
            password=self.password,
        )

    def create_demo_lots(self):
        for tag in LotTag.objects.filter(owner=self.institution):
            for name, archived in DEMO_LOTS.get(tag.name, []):
                Lot.objects.create(
                    name=name,
                    owner=self.institution,
                    archived=archived,
                    type=tag
                )

    def create_demo_b2c(self):
        lot = Lot.objects.get(name=B2C_LOT, owner=self.institution)
        devices = self.create_demo_devices()
        self.add_devices_to_lot(lot, devices)
        shop = self.subscribe_shop(lot)
        beneficiaries = self.create_beneficiaries(lot, shop)
        self.add_devices_to_beneficiary(beneficiaries[0], devices[:5])
        self.add_devices_to_beneficiary(beneficiaries[1], devices[5:6])

    def create_demo_devices(self):
        owner = User.objects.filter(institution=self.institution).first()
        if not owner:
            raise CommandError(f"No users found in institution '{self.institution}'.")

        before = {d.id for d in Device.get_all(self.institution)[0]}
        call_command(
            'add_demo_devices',
            self.institution.name,
            owner.email,
            str(B2C_DEVICES),
        )
        # get_all sorts by last activity descending, so reversing the new
        # entries restores the order in which add_demo_devices created them.
        after = Device.get_all(self.institution)[0]
        return [d for d in after if d.id not in before][::-1]

    def add_devices_to_lot(self, lot, devices):
        for dev in devices:
            lot.add(dev.id)

    def subscribe_shop(self, lot):
        shop_user = User.objects.get(email=B2C_SHOP, institution=self.institution)
        shop, _ = LotSubscription.objects.get_or_create(
            lot=lot,
            user=shop_user,
            defaults={'type': LotSubscription.Type.SHOP},
        )
        return shop

    def create_beneficiaries(self, lot, shop):
        return [
            Beneficiary.objects.create(email=email, lot=lot, shop=shop)
            for email in B2C_BENEFICIARIES
        ]

    def add_devices_to_beneficiary(self, beneficiary, devices):
        for dev in devices:
            beneficiary.add(dev.id)

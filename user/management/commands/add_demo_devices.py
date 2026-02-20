import uuid as _uuid

from django.core.management.base import BaseCommand, CommandError

from user.models import Institution, User
from evidence.parse import Build


MANUFACTURERS = ["Dell", "HP", "Lenovo", "Acer", "Asus", "Apple", "Toshiba"]
DEVICE_TYPES = [
    ("Laptop", "Laptop"),
    ("Desktop", "Tower"),
    ("Server", "Rack"),
]


class Command(BaseCommand):
    help = "Create synthetic demo devices for stress-testing"

    def add_arguments(self, parser):
        parser.add_argument('institution', type=str, help='Institution name')
        parser.add_argument('email', type=str, help='User email')
        parser.add_argument(
            'count', type=int, nargs='?', default=100,
            help='Number of devices to create (default: 100)',
        )

    def handle(self, *args, **kwargs):
        name = kwargs['institution']
        email = kwargs['email']
        count = kwargs['count']

        if count < 1:
            raise CommandError("count must be a positive integer.")

        try:
            institution = Institution.objects.get(name=name)
        except Institution.DoesNotExist:
            raise CommandError(f"Institution '{name}' not found.")

        try:
            user = User.objects.get(email=email, institution=institution)
        except User.DoesNotExist:
            raise CommandError(f"User '{email}' not found in institution '{name}'.")

        for i in range(1, count + 1):
            mfr = MANUFACTURERS[(i - 1) % len(MANUFACTURERS)]
            dev_type, chassis = DEVICE_TYPES[(i - 1) % len(DEVICE_TYPES)]
            snapshot = {
                "type": "Snapshot",
                "uuid": str(_uuid.uuid4()),
                "software": "Workbench",
                "version": "12.0b0",
                "device": {
                    "type": dev_type,
                    "manufacturer": mfr,
                    "model": f"Demo Model {i:04d}",
                    "serialNumber": f"DEMO{i:08d}",
                    "chassis": chassis,
                },
                "components": [],
            }
            Build(snapshot, user)

        self.stdout.write(
            self.style.SUCCESS(f"Created {count} devices for institution '{name}'.")
        )

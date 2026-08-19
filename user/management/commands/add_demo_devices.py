import os
import json
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
        parser.add_argument(
            '--output-dir', type=str, default=None,
            help='Write snapshots as json files in this directory instead of '
                 'processing them, so they can be uploaded manually',
        )

    def handle(self, *args, **kwargs):
        name = kwargs['institution']
        email = kwargs['email']
        count = kwargs['count']
        output_dir = kwargs['output_dir']

        if count < 1:
            raise CommandError("count must be a positive integer.")

        user = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        else:
            try:
                institution = Institution.objects.get(name=name)
            except Institution.DoesNotExist:
                raise CommandError(f"Institution '{name}' not found.")

            try:
                user = User.objects.get(email=email, institution=institution)
            except User.DoesNotExist:
                raise CommandError(
                    f"User '{email}' not found in institution '{name}'."
                )

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
            if output_dir:
                path = os.path.join(output_dir, f"demo-{i:05d}.json")
                with open(path, 'w') as snapshot_file:
                    json.dump(snapshot, snapshot_file)
            else:
                Build(snapshot, user)

        if output_dir:
            msg = f"Wrote {count} snapshots in '{output_dir}'."
        else:
            msg = f"Created {count} devices for institution '{name}'."

        self.stdout.write(self.style.SUCCESS(msg))

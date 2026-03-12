import json
import hashlib
import logging

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.conf import settings

from evidence.models import SystemProperty, RootAlias
from evidence.parse import Build
from evidence.xapian import search


logger = logging.getLogger('django')


class Command(BaseCommand):
    help = "Create RootAlias entries mapping old algorithm HIDs to the current algorithm HID"

    def handle(self, *args, **kwargs):
        self.new_algo = settings.DEVICEHUB_ALGORITHM_DEVICE
        self.stdout.write(f"Current algorithm: {self.new_algo}")

        self.old_algos = ["ereuse24"]

        self.get_old_properties()

        created = 0
        skipped = 0
        errors = 0

        for prop in self.old_props:
            user = prop.user or prop.owner.user_set.filter(is_admin=True).first()

            evidence_json = self.get_snapshot(prop.owner, str(prop.uuid))
            if evidence_json is None:
                errors += 1
                continue

            new_hid_raw = self.get_new_hid_raw(evidence_json, user)
            if new_hid_raw is None:
                skipped += 1
                continue

            if self.create_alias(prop, new_hid_raw, user):
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            f"\nDone: {created} created, {skipped} skipped, {errors} errors"
        )

    def get_old_properties(self):
        already_migrated = SystemProperty.objects.filter(
            uuid=OuterRef('uuid'),
            key=self.new_algo,
        )

        self.old_props = SystemProperty.objects.filter(
            key__in=self.old_algos
        ).exclude(
            Exists(already_migrated)
        )

        total = self.old_props.count()
        self.stdout.write(f"Found {total} SystemProperty entries with old algorithms")

    def get_snapshot(self, institution, uuid):
        qs = 'uuid:"{}"'.format(uuid)
        matches = search(institution, qs, limit=1)
        if not matches or matches.size() == 0:
            self.stdout.write(self.style.WARNING(f"  No xapian doc for uuid={uuid}"))
            return None

        snap_data = next(iter(matches)).document.get_data()
        if isinstance(snap_data, bytes):
            snap_data = snap_data.decode('utf-8')

        try:
            return json.loads(snap_data)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Invalid JSON for uuid={uuid}: {e}"))
            return None

    def get_new_hid_raw(self, evidence_json, user):
        try:
            b = Build(evidence_json, user, check=True)
            hid_raw = b.build.algorithms.get(self.new_algo)
        except Exception as e:
            uuid = evidence_json.get('uuid', '?')
            self.stdout.write(self.style.ERROR(f"  Parse failed for uuid={uuid}: {e}"))
            return None

        if not hid_raw:
            uuid = evidence_json.get('uuid', '?')
            self.stdout.write(
                self.style.WARNING(f"  Algorithm {self.new_algo} not found for uuid={uuid}")
            )
        return hid_raw

    def create_alias(self, prop, new_hid_raw, user):
        new_hash = hashlib.sha3_256(new_hid_raw.encode()).hexdigest()
        alias = f"{self.new_algo}:{new_hash}"
        root = prop.value

        if RootAlias.objects.filter(owner=prop.owner, alias=alias).exists():
            self.stdout.write(f"  Skip (exists): {alias}")
            return False

        RootAlias.objects.create(owner=prop.owner, user=user, alias=alias, root=root)
        self.stdout.write(self.style.SUCCESS(f"  Created: alias={alias}, root={root}"))
        return True

import json
import hashlib
import logging

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.test.utils import override_settings

from evidence.models import SystemProperty, RootAlias
from evidence.parse import Build
from evidence.xapian import search
from utils.constants import DEVICE_IDENTITY_ALGOS


logger = logging.getLogger('django')


class Command(BaseCommand):
    help = (
        "Create RootAlias entries mapping the existing device HIDs to the HID "
        "of a target algorithm, so devices stay reachable when the active "
        "algorithm changes. Pass the target as a positional argument; the HID "
        "is recomputed as if that algorithm were active, so this can run "
        "before flipping DEVICEHUB_ALGORITHM_DEVICE in the environment. "
        "Mapping from every other identity algorithm (not just the active one) "
        "keeps it resilient across multi-version jumps."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "algo",
            choices=DEVICE_IDENTITY_ALGOS,
            help="target algorithm to migrate HIDs to (e.g. ereuse26)",
        )

    def handle(self, *args, **kwargs):
        self.target_algo = kwargs["algo"]
        self.source_algos = [a for a in DEVICE_IDENTITY_ALGOS if a != self.target_algo]
        self.stdout.write(f"Target algorithm: {self.target_algo}")
        self.stdout.write(f"Source algorithms: {self.source_algos}")

        # Recompute HIDs as if the target algorithm were the active one, so the
        # aliases match what new snapshots will produce once the environment is
        # switched. Works in both directions (e.g. ereuse24 -> ereuse26 and back).
        with override_settings(DEVICEHUB_ALGORITHM_DEVICE=self.target_algo):
            self._run()

    def _run(self):
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
            key=self.target_algo,
        )

        self.old_props = SystemProperty.objects.filter(
            key__in=self.source_algos
        ).exclude(
            Exists(already_migrated)
        )

        total = self.old_props.count()
        self.stdout.write(f"Found {total} SystemProperty entries to migrate")

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
            hid_raw = b.build.algorithms.get(self.target_algo)
        except Exception as e:
            uuid = evidence_json.get('uuid', '?')
            self.stdout.write(self.style.ERROR(f"  Parse failed for uuid={uuid}: {e}"))
            return None

        if not hid_raw:
            uuid = evidence_json.get('uuid', '?')
            self.stdout.write(
                self.style.WARNING(
                    f"  Algorithm {self.target_algo} not found for uuid={uuid}"
                )
            )
        return hid_raw

    def create_alias(self, prop, new_hid_raw, user):
        new_hash = hashlib.sha3_256(new_hid_raw.encode()).hexdigest()
        alias = f"{self.target_algo}:{new_hash}"

        if RootAlias.objects.filter(owner=prop.owner, alias=alias).exists():
            self.stdout.write(f"  Skip (exists): {alias}")
            return False

        root = RootAlias.resolve_root(prop.owner, prop.value)
        RootAlias.set_alias(prop.owner, alias, root, user=user)
        self.stdout.write(self.style.SUCCESS(f"  Created: alias={alias}, root={root}"))
        return True

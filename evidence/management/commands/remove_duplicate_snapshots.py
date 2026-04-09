"""
Remove duplicate snapshot files from the evidences directory.
Duplicate key: UUID + institution.
The oldest file (by date in filename) is kept; newer copies are deleted.

Usage:
    manage.py deduplicatesnapshots [--confirm]

Without --confirm runs as a dry-run and only shows what would be deleted.
"""
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand


def parse_date_from_filename(filename):
    name = filename.rsplit("_", 1)[0]
    try:
        return datetime.strptime(name, "%Y-%m-%d-%H-%M")
    except ValueError:
        return None


def get_uuid_from_filename(filename):
    parts = filename.rsplit("_", 1)
    if len(parts) != 2:
        return None
    return parts[1].replace(".json", "")


def find_duplicates(snapshots_path):
    by_uuid = {}

    for f in os.listdir(snapshots_path):
        if not f.endswith(".json"):
            continue
        f_path = os.path.join(snapshots_path, f)
        if not os.path.isfile(f_path):
            continue

        uuid = get_uuid_from_filename(f)
        date = parse_date_from_filename(f)

        if not uuid or not date:
            continue

        by_uuid.setdefault(uuid, []).append((date, f_path))

    duplicates = {}
    for uuid, entries in by_uuid.items():
        if len(entries) > 1:
            duplicates[uuid] = sorted(entries, key=lambda x: x[0])

    return duplicates


class Command(BaseCommand):
    help = "Remove duplicate snapshot files from the evidences directory (keeps the oldest)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Perform the deletion. Without this flag only shows what would be deleted (dry-run).",
        )

    def handle(self, *args, **options):
        evidences_dir = settings.EVIDENCES_DIR
        dry_run = not options["confirm"]

        if dry_run:
            self.stdout.write("--- DRY-RUN: nothing will be deleted (use --confirm to delete) ---\n")

        total_deleted = 0
        total_kept = 0

        for institution_uuid in os.listdir(evidences_dir):
            institution_path = os.path.join(evidences_dir, institution_uuid)
            snapshots_path = os.path.join(institution_path, "snapshots")

            if not os.path.isdir(snapshots_path):
                continue

            duplicates = find_duplicates(snapshots_path)

            if not duplicates:
                self.stdout.write(f"[{institution_uuid}] No duplicates found.")
                continue

            self.stdout.write(f"[{institution_uuid}] {len(duplicates)} UUIDs with duplicates:")

            for uuid, entries in duplicates.items():
                kept_date, kept_path = entries[0]
                to_delete = entries[1:]

                self.stdout.write(f"  {uuid}")
                self.stdout.write(f"    keep   ({kept_date:%Y-%m-%d %H:%M}): {os.path.basename(kept_path)}")
                for date, path in to_delete:
                    self.stdout.write(f"    delete ({date:%Y-%m-%d %H:%M}): {os.path.basename(path)}")
                    if not dry_run:
                        os.remove(path)
                    total_deleted += 1

                total_kept += 1

        action = "deleted" if not dry_run else "to delete"
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal: {total_kept} kept, {total_deleted} {action}.")
        )

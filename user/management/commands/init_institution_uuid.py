import os
import uuid
import shutil

from django.core.management.base import BaseCommand
from django.conf import settings

from user.models import Institution


class Command(BaseCommand):
    help = "Generate UUID for each institution and rename its directory in EVIDENCES_DIR"

    def handle(self, *args, **kwargs):
        institutions = Institution.objects.all()

        if not institutions.exists():
            self.stdout.write("No institutions found.")
            return

        for institution in institutions:
            # Step 1: assign UUID if not set
            if not institution.uuid:
                institution.uuid = uuid.uuid4()
                institution.save(update_fields=['uuid'])
                self.stdout.write(f"Generated UUID for '{institution.name}': {institution.uuid}")
            else:
                self.stdout.write(f"Institution '{institution.name}' already has UUID: {institution.uuid}")

            # Step 2: rename directory in EVIDENCES_DIR
            old_path = os.path.join(settings.EVIDENCES_DIR, institution.name)
            new_path = os.path.join(settings.EVIDENCES_DIR, str(institution.uuid))

            if os.path.isdir(old_path):
                if os.path.exists(new_path):
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Skipping rename: target '{new_path}' already exists"
                        )
                    )
                else:
                    shutil.move(old_path, new_path)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Renamed: '{old_path}' -> '{new_path}'"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Directory not found: '{old_path}' (skipping)"
                    )
                )

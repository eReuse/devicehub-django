import os
import json
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from utils.device import create_property, create_doc, create_index
from user.models import Institution
from evidence.parse import Build


logger = logging.getLogger('django')


class Command(BaseCommand):
    help = "Reindex snapshots"
    EVIDENCES = settings.EVIDENCES_DIR

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-index",
            action="store_true",
            help=(
                "Rebuild the xapian index only. SystemProperty rows and the "
                "dlt registration are left untouched, so the index is "
                "restored against whatever the database already holds."
            ),
        )

    def handle(self, *args, **kwargs):
        self.only_index = kwargs["only_index"]

        if os.path.isdir(self.EVIDENCES):
            self.read_files(self.EVIDENCES)

    def read_files(self, directory):
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if not os.path.isdir(filepath):
                continue

            institution = Institution.objects.filter(name=filename).first()

            if not institution:
                continue

            user = institution.users.filter(is_admin=True).first()
            if not user:
                txt = "No there are Admins for the institution: %s"
                logger.warning(txt, institution.name)
                continue

            for subdir in ["snapshots", "placeholders"]:
                self.read_snapshots(os.path.join(filepath, subdir), user)

    def read_snapshots(self, directory, user):
        if not os.path.isdir(directory):
            logger.error("No such directory: %s", directory)
            return

        for f in os.listdir(directory):
            f_path = os.path.join(directory, f)
            if f_path[-5:] == ".json" and os.path.isfile(f_path):
                self.process(f_path, user)

    def process(self, filepath, user):
        try:
            with open(filepath, 'r') as f:
                content = json.loads(f.read())
        except Exception:
            logger.warning("Not can open %s", filepath)
            return

        if content.get("type") == "Websnapshot":
            self.build_placeholder(content, user, filepath)
        else:
            self.build_snapshot(content, user, filepath)

    def build_placeholder(self, s, user, f_path):
        try:
            create_index(s, user)
            if not self.only_index:
                create_property(s, user, commit=True)
        except Exception as err:
            logger.warning("In placeholder %s \n%s", f_path, err)

    def build_snapshot(self, s, user, f_path):
        try:
            if self.only_index:
                # check=True picks the parser without writing anything
                build = Build(s, user, check=True)
                if build.build.uuid:
                    build.index()
                return

            Build(s, user)
        except Exception:
            logger.error("Error: in Snapshot %s", f_path)

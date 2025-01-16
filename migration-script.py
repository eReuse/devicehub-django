import os
import json
import django
import logging
import argparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhub.settings')

django.setup()

from django.contrib.auth import get_user_model

from utils.save_snapshots import move_json, save_in_disk
from evidence.parse import Build
from evidence.models import Annotation


logger = logging.getLogger(__name__)

User = get_user_model()

SEPARATOR = ";"
PATH_SNAPTHOPS = "examples/snapshots"


### read csv ###
def get_dict(row, header):
    if not row or not header:
        return
    if len(row) != len(header):
        return

    return {row[i]: header[i] for i in range(len(header))}


def open_csv(csv):
    # return a list of dictionaries whith the header of csv as keys of the dicts
    with open(csv) as f:
        _file = f.read()

    rows = _file.split("\n")
    if len(rows) < 2:
        return []

    header = rows[0].split(SEPARATOR)
    data = []
    for row in rows[1:]:
        drow = get_dict(row.split(SEPARATOR), header)
        if drow:
            data.append(drow)
    return data
### end read csv ###


### read snapshot ###
def search_snapshot_from_uuid(uuid):
    # search snapshot from uuid
    for root, _, files in os.walk(PATH_SNAPTHOPS):
        for f in files:
            if uuid in f:
                return os.path.join(root, f)


def open_snapshot(uuid):
    snapshot_path = search_snapshot_from_uuid(uuid)
    if not snapshot_path:
        return None, None

    with open(snapshot_path) as f:
        try:
            snap = json.loads(f.read())
        except Exception as err:
            logger.error("uuid: {}, error: {}".format(uuid, err))
            return None, None
    return snap, snapshot_path
### end read snapshot ###

### migration ###
def create_custom_id(dhid, uuid, user):
    tag = Annotation.objects.filter(
        uuid=uuid,
        type=Annotation.Type.SYSTEM,
        key='CUSTOM_ID',
        owner=user.institution
    ).first()

    if tag:
        return

    Annotation.objects.create(
        uuid=uuid,
        type=Annotation.Type.SYSTEM,
        key='CUSTOM_ID',
        value=dhid,
        owner=user.institution,
        user=user
    )


def migrate_snapshots(row, user):
    # import pdb; pdb.set_trace()
    if not row or not user:
        return
    dhid = row.get("dhid")
    uuid = row.get("uuid")
    snapshot, snapshot_path = open_snapshot(uuid)
    if not snapshot or not snapshot_path:
        return

    # insert snapshot
    path_name = save_in_disk(snapshot, user.institution.name)
    Build(path_name, user)
    move_json(path_name, user.institution.name)

    # insert dhid
    create_custom_id(dhid, uuid)

### end migration ###


### initial main ###
def prepare_logger():

    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] workbench: %(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def parse_args():
    """
    Parse config argument, if available
    """
    parser = argparse.ArgumentParser(
        usage="migration-script.py [-h] [--csv CSV]",
        description="Csv file with datas to migratie.")
    parser.add_argument(
        '--csv',
        help="path to the data file."
    )
    parser.add_argument(
        '--email',
        help="email of user.",
    )
    parser.add_argument(
        '--snapshots',
        help="dir where reside the snapshots.",
    )
    return parser.parse_args()


def main():
    prepare_logger()
    logger.info("START")
    args = parse_args()

    PATH_SNAPTHOPS = args.snapshots
    user = User.objects.get(email=args.email)

    for row in open_csv(args.csv):
        migrate_snapshots(row, user)


if __name__ == '__main__':
    main()

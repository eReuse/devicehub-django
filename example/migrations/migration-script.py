import os
import json
import django
import logging
import argparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhub.settings')

django.setup()

from datetime import datetime
from django.contrib.auth import get_user_model

from utils.save_snapshots import move_json, save_in_disk
from evidence.parse import Build
from evidence.models import SystemProperty
from lot.models import Lot, LotTag, DeviceLot


logger = logging.getLogger(__name__)

User = get_user_model()

SEPARATOR = ";"
QUOTA = '"'
PATH_SNAPTHOPS = "examples/snapshots"


### read csv ###
def get_dict(row, header):
    if not row or not header:
        return
    if len(row) != len(header):
        return

    return {header[i]: row[i] for i in range(len(header))}


def open_csv(csv):
    # return a list of dictionaries whith the header of csv as keys of the dicts
    with open(csv) as f:
        _file = f.read()

    rows = _file.split("\n")
    if len(rows) < 2:
        return []

    header = [x.replace(QUOTA, '') for x in rows[0].split(SEPARATOR)]
    data = []
    for row in rows[1:]:
        lrow = [x.replace(QUOTA, '') for x in row.split(SEPARATOR)]
        drow = get_dict(lrow, header)
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


### migration snapshots ###
def create_custom_id(dhid, uuid, user, created):

    if not uuid or not dhid:
        return

    tag = SystemProperty.objects.filter(
        uuid=uuid,
        key='CUSTOM_ID',
        owner=user.institution
    ).first()

    if tag or not uuid or not dhid:
        return

    dcreated = datetime.strptime(created+"00", "%Y-%m-%d %H:%M:%S.%f%z")

    SystemProperty.objects.create(
        uuid=uuid,
        key='CUSTOM_ID',
        value=dhid,
        owner=user.institution,
        user=user
    )

    for obj in SystemProperty.objects.filter(uuid=uuid):
        obj.created = dcreated
        obj.save()


def migrate_snapshots(row, user):
    if not row or not user:
        return

    dhid = row.get("dhid")
    uuid = row.get("uuid")
    created = row.get("created")
    snapshot, snapshot_path = open_snapshot(uuid)
    if not snapshot or not snapshot_path:
        return

    logger.info(snapshot.get("version"))
    # if snapshot.get('version') == "2022.12.2-beta":
    #     return

    # insert snapshot
    path_name = save_in_disk(snapshot, user.institution.name)
    Build(snapshot, user)
    move_json(path_name, user.institution.name)

    # insert dhid
    try:
        create_custom_id(dhid, uuid, user, created)
    except Exception as err:
        logger.error(err)
        logger.error("DHID: %s uuid: %s", dhid, uuid)

### end migration snapshots ###


### migration lots ###
def migrate_lots(row, user):
    tag = row.get("type", "Temporal")
    name = row.get("name")
    ltag = LotTag.objects.filter(name=tag, owner=user.institution).first()
    if tag and not ltag:
        ltag = LotTag.objects.create(
            name=tag,
            owner=user.institution,
            user=user
        )

    if Lot.objects.filter(name=name, owner=user.institution).first():
        return

    Lot.objects.create(
        name=name,
        owner=user.institution,
        user=user,
        type=ltag
    )


def add_device_in_lot(row, user):
    lot_name = row.get("lot_name")
    dhid = row.get("dhid")

    if not lot_name or not dhid:
        return

    dev = SystemProperty.objects.filter(
        key='CUSTOM_ID',
        value=dhid,
        owner=user.institution,
    ).first()

    if not dev:
        logger.warning("Not exist dhid %s", dhid)
        return

    lot = Lot.objects.filter(
        name=lot_name,
        owner=user.institution,
        user=user,
    ).first()

    if not lot:
        return

    if DeviceLot.objects.filter(lot=lot, device_id=dhid).exists():
        return

    DeviceLot.objects.create(lot=lot, device_id=dhid)

### end migration lots ###


### initial main ###
def prepare_logger():

    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] migrate: %(levelname)s: %(message)s')
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
        '--csv-dhid',
        help="path to the csv file with relation dhid and uuid."
    )
    parser.add_argument(
        '--lots',
        help="path to the csv file with relation lot_name and type of lot."
    )
    parser.add_argument(
        '--csv-lots-dhid',
        help="path to the csv file with relation lot_name and type of lot."
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
    user = User.objects.get(email=args.email)

    if args.snapshots:
        global PATH_SNAPTHOPS
        PATH_SNAPTHOPS = args.snapshots

    if args.csv_dhid:
    # migration snapthots
        for row in open_csv(args.csv_dhid):
            migrate_snapshots(row, user)

    # migration lots
    if args.lots:
        for row in open_csv(args.lots):
            migrate_lots(row, user)

    # migration dhids in lots
    if args.csv_lots_dhid:
        for row in open_csv(args.csv_lots_dhid):
            add_device_in_lot(row, user)

if __name__ == '__main__':
    main()

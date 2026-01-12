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
from utils.device import create_property, create_doc, create_index
from evidence.parse import Build
from evidence.models import SystemProperty, RootAlias
from lot.models import Lot, LotTag, DeviceLot


logger = logging.getLogger(__name__)

User = get_user_model()

SEPARATOR = ";"
QUOTA = '"'
PATH_SNAPSHOTS = "examples/snapshots"
USER_ID = "cac4a45a-71a9-4a57-8d08-4032fc0bee2c"


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


### migration snapshots ###
def create_dhid(row, user):

    dhid = row.get("dhid").lower()
    uuid = row.get("uuid")
    created = row.get("created")

    if not uuid or not dhid or not created:
        return

    sp = SystemProperty.objects.filter(
        uuid=uuid,
        owner=user.institution
    ).first()

    if not sp:
        logger.error("DHID: %s no exist the snapshot uuid: %s", dhid, uuid)
        return

    root_alias = RootAlias.objects.filter(
        owner=user.institution,
        alias=sp.value
    ).first()

    if root_alias:
        if root_alias.root != f"custom_id:{dhid}":
            logger.error("RootAlias Duplicate %s - %s", root_alias.root, dhid)
        return

    dcreated = datetime.strptime(created+"00", "%Y-%m-%d %H:%M:%S.%f%z")

    RootAlias.objects.create(
        created=dcreated,
        alias=sp.value,
        root="custom_id:{}".format(dhid),
        owner=user.institution,
        user=user
    )

    sp.created = dcreated
    sp.save()


def create_monitor(row, user):
    row["type"] = "Display"
    dhid = row.pop("dhid", '').lower()
    created = row.pop("created", None)
    doc = create_doc(row)
    # path_name = save_in_disk(doc, user.institution.name, place="placeholder")
    create_index(doc, user)
    sp = create_property(doc, user, commit=True)
    # move_json(path_name, user.institution.name, place="placeholder")

    root_alias = RootAlias.objects.filter(
        owner=user.institution,
        alias=sp.value
    ).first()

    if root_alias:
        if root_alias.root != f"custom_id:{dhid}":
            logger.error("RootAlias Duplicate %s - %s", root_alias.root, dhid)
        return

    dcreated = datetime.strptime(created+"00", "%Y-%m-%d %H:%M:%S.%f%z")

    RootAlias.objects.create(
        created=dcreated,
        alias=sp.value,
        root="custom_id:{}".format(dhid),
        owner=user.institution,
        user=user
    )

    sp.created = dcreated
    sp.save()


def migrate_snapshots(snap_path, user):

    with open(snap_path) as _f:
        s = _f.read()
        if 'ComputerMonitor' in s:
            return

        snapshot = json.loads(s)

    logger.info(snapshot.get("version"))
    # if snapshot.get('version') == "2022.12.2-beta":
    #     return

    # insert snapshot
    path_name = save_in_disk(snapshot, user.institution.name)
    build = Build(snapshot, user)
    move_json(path_name, user.institution.name)

    for s in SystemProperty.objects.filter(owner=user.institution, uuid=build.uuid):
        timestamp = snapshot.get("timestamp") or snapshot.get("endTime")
        if not timestamp:
            continue

        if "+" not in timestamp and "Z" not in timestamp and "-" in timestamp:
            timestamp += "+00:00"

        timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")

        s.created = timestamp
        s.save()

### end migration snapshots ###


### migration lots ###
def create_lots(row, user):
    lot_name = row.get("lot_name")
    incoming = row.get("incoming")
    outgoing = row.get("outgoing")

    lot = Lot.objects.filter(name=lot_name, owner=user.institution).first()
    if lot:
        return lot

    tag = "Temporal"
    if incoming:
        tag = "Entrada"
    elif outgoing:
        tag = "Salida"

    ltag = LotTag.objects.filter(name=tag, owner=user.institution).first()

    lot = Lot.objects.create(
        name=lot_name,
        owner=user.institution,
        user=user,
        type=ltag
    )
    return lot


def add_device_in_lot(row, user):
    lot_name = row.get("lot_name")
    dhid = row.get("dhid").lower()

    if not lot_name or not dhid:
        return

    lot = create_lots(row, user)

    if not lot:
        logger.error("Not exist lot %s", lot_name)
        return

    alias = RootAlias.objects.filter(
        owner=user.institution,
        root=f"custom_id:{dhid}"
    ).first()

    if not alias:
        logger.error("Not exist %s in RootAlias", dhid)
        return

    dev = SystemProperty.objects.filter(
        value=alias.alias,
        owner=user.institution,
    ).first()

    if not dev:
        logger.warning("Not exist dhid %s in Systemproperty", dhid)
        return

    if DeviceLot.objects.filter(lot=lot, device_id=dhid).exists():
        return

    if not DeviceLot.objects.filter(lot=lot, device_id=dev.value).first():
        DeviceLot.objects.create(lot=lot, device_id=dev.value)

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
    parser.add_argument(
        '--monitors',
        help="path to the csv file with monitor details."
    )
    return parser.parse_args()


def main():
    prepare_logger()
    logger.info("START")
    args = parse_args()
    user = User.objects.get(email=args.email)

    if args.snapshots:
        global PATH_SNAPTHOPS
        PATH_SNAPSHOTS = args.snapshots
        for p in os.listdir(args.snapshots):
            if p[-4:] == "json":
                snap = f"{PATH_SNAPSHOTS}/{p}"
                try:
                    migrate_snapshots(snap, user)
                except Exception as err:
                    logger.error(err)
                    logger.error("snap: %s", snap)

    if args.csv_dhid:
        for row in open_csv(args.csv_dhid):
            try:
                create_dhid(row, user)
            except Exception as err:
                logger.error(err)
                logger.error("row: %s", row)

    # migration dhids in lots
    if args.csv_lots_dhid:
        for row in open_csv(args.csv_lots_dhid):
            add_device_in_lot(row, user)

    if args.monitors:
        for row in open_csv(args.monitors):
            try:
                create_monitor(row, user)
            except Exception as err:
                logger.error(err)

if __name__ == '__main__':
    main()

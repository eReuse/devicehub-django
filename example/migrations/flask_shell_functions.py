import os
import json

from flask import g
from ereuse_devicehub.resources.user.models import User
from ereuse_devicehub.resources.action.models import Snapshot
from ereuse_devicehub.resources.lot.models import Lot
from ereuse_devicehub.resources.device.models import ComputerMonitor, Monitor, Computer




# ==============    COMPUTERS    ================== #
def generate_computers(email):
    u = User.query.filter(User.email==email).first()
    g.user = u
    dhids = [["dhid", "uuid", "created"]]
    devsLots = [["lot_name", "dhid", "incoming", "outgoing"]]
    PATH_SNAPSHOTS = "2026-01-05/snapshots"
    uuids = []

    # get uuids form real snapshots
    for p in os.listdir(PATH_SNAPSHOTS):
        if p[-4:] == "json":
            snap_path = f"{PATH_SNAPSHOTS}/{p}"
            with open(snap_path) as _f:
                s = _f.read()
                if 'ComputerMonitor' in s:
                    continue
                uuid = json.loads(s).get("uuid")
                if uuid:
                    uuids.append(uuid)


    # generate dhids and relations dhid-lots data
    for s in Snapshot.query.filter(Snapshot.author==u, Snapshot.uuid.in_(uuids)):
        d = s.created.strftime("%Y-%m-%d %H:%M:%S.%f%z")
        try:
            c = s.device.binding.device
            dhids.append([c.devicehub_id, str(s.uuid), d])

            for l in c.lots:
                devsLots.append([
                    l.name,
                    c.devicehub_id,
                    l.is_incoming and "1" or "",
                    l.is_outgoing and "1" or ""
                ])
        except Exception:
            continue


    # white files
    with open("dhids.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in dhids]))


    with open("devices-lots.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in devsLots]))


# ==============    MONITORS    ================== #
def generate_monitors(email):
    u = User.query.filter(User.email==email).first()
    g.user = u
    monitors = [["dhid", "manufacturer", "model", "serial_number", "created", "type"]]
    mlots = [["lot_name", "dhid", "incoming", "outgoing"]]

    for c in ComputerMonitor.query.filter_by(owner=u):
        d = c.created.strftime("%Y-%m-%d %H:%M:%S.%f%z")
        monitors.append([c.devicehub_id, c.manufacturer, c.model, c.serial_number, d, "Display"])
        for l in c.lots:
            mlots.append([l.name, c.devicehub_id, l.is_incoming and "1" or "", l.is_outgoing and "1" or ""])

    for c in Monitor.query.filter_by(owner=u):
        d = c.created.strftime("%Y-%m-%d %H:%M:%S.%f%z")
        monitors.append([c.devicehub_id, c.manufacturer, c.model, c.serial_number, d, "Display"])
        for l in c.lots:
            mlots.append([l.name, c.devicehub_id, l.is_incoming and "1" or "", l.is_outgoing and "1" or ""])


    with open("monitors.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in monitors]))

    with open("monitors-lots.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in mlots]))


def generate_placeholder(email):
    u = User.query.filter(User.email==email).first()
    g.user = u
    computers = [["dhid", "manufacturer", "model", "serial_number", "created", "type"]]
    clots = [["lot_name", "dhid", "incoming", "outgoing"]]

    for c in Computer.query.filter_by(owner=u):
        if not c.placeholder or c.placeholder.binding:
            continue

        d = c.created.strftime("%Y-%m-%d %H:%M:%S.%f%z")
        ctype = c.type
        if ctype == "Computer":
            ctype = "Desktop"

        computers.append([c.devicehub_id or '', c.manufacturer or '', c.model or '', c.serial_number or '', d, ctype])

        if c.devicehub_id:
            for l in c.lots:
                clots.append([l.name, c.devicehub_id, l.is_incoming and "1" or "", l.is_outgoing and "1" or ""])

    with open("placeholders.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in computers]))

    with open("placeholders-lots.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in clots]))


def generate_rel_lot_devs(email):
    u = User.query.filter(User.email==email).first()
    g.user = u
    devs = [["lot_name", "total"]]

    for l in Lot.query.filter_by(owner=u):
        devs.append([l.name, "{}".format(len(l.devices))])

    with open("lots_count.csv", "w") as _f:
        _f.write("\n".join([";".join(l) for l in devs]))


def backup(email):
    generate_computers(email)
    generate_monitors(email)
    generate_placeholder(email)
    generate_rel_lot_devs(email)

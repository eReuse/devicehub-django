import os
import json
from flask import g
from ereuse_devicehub.resources.user.models import User
from ereuse_devicehub.resources.action.models import Snapshot
from ereuse_devicehub.resources.lot.models import Lot
from ereuse_devicehub.resources.device.models import ComputerMonitor

u = User.query.filter(User.email=="user@example.org").first()
g.user = u


dhids = [["dhid", "uuid", "created"]]
devsLots = [["lot_name", "dhid", "incoming", "outgoing"]]

# ==============    COMPUTERS    ================== #
PATH_SNAPSHOTS = "2026-01-05/snapshots"
uuids = []
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


with open("dhids.csv", "w") as _f:
    _f.write("\n".join([";".join(l) for l in dhids]))


with open("devices-lots.csv", "w") as _f:
    _f.write("\n".join([";".join(l) for l in devsLots]))


# ==============    MONITORS    ================== #
monitors = [["dhid", "manufacturer", "model", "serial_number", "created"]]
mlots = [["lot_name", "dhid", "incoming", "outgoing"]]

for c in ComputerMonitor.query.filter_by(owner=u):
    d = c.created.strftime("%Y-%m-%d %H:%M:%S.%f%z")
    monitors.append([c.devicehub_id, c.manufacturer, c.model, c.serial_number, d])
    for l in c.lots:
        mlots.append([l.name, c.devicehub_id, l.is_incoming and "1" or "", l.is_outgoing and "1" or ""])


with open("monitors.csv", "w") as _f:
    _f.write("\n".join([";".join(l) for l in monitors]))

with open("monitors-lots.csv", "w") as _f:
    _f.write("\n".join([";".join(l) for l in mlots]))

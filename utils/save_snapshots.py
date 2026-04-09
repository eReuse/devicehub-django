import os
import json
import shutil

from datetime import datetime
from django.conf import settings


def move_json(path_name, user, place="snapshots"):
    if place != "snapshots":
        place = "placeholders"

    tmp_snapshots = settings.EVIDENCES_DIR
    path_dir = os.path.join(tmp_snapshots, str(user), place)

    if os.path.isfile(path_name):
        shutil.copy(path_name, path_dir)
        os.remove(path_name)


def save_in_disk(data, user, place="snapshots"):
    uuid = data.get("uuid")
    if data.get("credentialSubject"):
        uuid = data["credentialSubject"].get("uuid")

    now = datetime.now()
    year = now.year
    month = now.month
    day = now.day
    hour = now.hour
    minutes = now.minute
    tmp_snapshots = settings.EVIDENCES_DIR
    if place != "snapshots":
        place = "placeholders"

    name_file = f"{year}-{month}-{day}-{hour}-{minutes}_{uuid}.json"
    path_dir = os.path.join(tmp_snapshots, str(user), place, "errors")
    path_name = os.path.join(path_dir, name_file)

    os.makedirs(path_dir, exist_ok=True)

    with open(path_name, 'w') as snapshot_file:
        snapshot_file.write(json.dumps(data))

    return path_name

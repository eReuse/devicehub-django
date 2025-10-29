import logging

from evidence import (
    display_parse_details,
    disk_parse_details,
    legacy_parse_details,
    normal_parse_details,
    old_parse_details
)


logger = logging.getLogger('django')


class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
       if snapshot.get("credentialSubject"):
           self.build = normal_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )
       elif snapshot.get("software") != "workbench-script":
           self.build = old_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )
       elif snapshot.get("data",{}).get("lshw"):
           self.build = legacy_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )
       elif snapshot.get("data",{}).get("snapshot_type") == "Display":
           self.build = display_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )
       elif snapshot.get("data",{}).get("snapshot_type") == "Disk":
           self.build = disk_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )
       else:
           self.build = normal_parse_details.ParseSnapshot(
               snapshot,
               default=default
           )

       self.default = default
       self.device = self.build.snapshot_json.get("device")
       self.components = self.build.snapshot_json.get("components")

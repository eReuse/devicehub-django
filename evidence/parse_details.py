import logging

from evidence import (
    legacy_parse_details,
    normal_parse_details,
    old_parse_details,
    universal_parse_details,
)
from evidence.sources import Sources, detect, WB11, LEGACY, INXI, DMI


logger = logging.getLogger('django')

DETAIL_BUILDERS = {
    WB11: old_parse_details.ParseSnapshot,
    LEGACY: legacy_parse_details.ParseSnapshot,
    INXI: normal_parse_details.ParseSnapshot,
    DMI: universal_parse_details.ParseSnapshot,
}


class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        sources = Sources(snapshot)
        builder = DETAIL_BUILDERS.get(
            detect(sources), normal_parse_details.ParseSnapshot
        )
        self.build = builder(sources.snapshot, default=default)

        self.default = default
        self.device = self.build.snapshot_json.get("device")
        self.components = self.build.snapshot_json.get("components", [])

import logging


logger = logging.getLogger('django')


class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        self.default = default
        self.snapshot_json = snapshot

        self.device = snapshot.get("device")
        self.components = snapshot.get("components", [])
        for c in self.components:
            c.pop("actions", None)

import json
import logging

logger = logging.getLogger('django')

# Content formats (after the envelope has been unwrapped).
WB11 = "wb11"        # ships a ready-made 'device' (workbench 11 and Web snapshots)
LEGACY = "legacy"    # lshw/hwinfo (workbench-script targeting devicehub-teal)
INXI = "inxi"        # regular workbench-script on Linux
DMI = "dmi"          # dmidecode only (Windows/macOS)

# Keys that reveal a snapshot nested inside another 'data' (the
# DeviceSnapshotV1 envelope the wallet returns when it fails to sign the VC).
_NESTED_MARKERS = ("software", "operator_id")


class Sources:
    """Normalize a snapshot envelope and expose the resolved command outputs,
    regardless of the wrapper:

    1. Plain: the snapshot carries the commands in ``data{}``.
    2. Signed VC: the snapshot lives in ``credentialSubject`` and the commands
       in ``evidence[]`` (each one {operation, output}).
    3. Unsigned DeviceSnapshotV1: the real snapshot is nested in
       ``snapshot["data"]`` and must be unwrapped.
    """

    def __init__(self, snapshot):
        self.raw = snapshot
        self.snapshot = self._unwrap(snapshot)
        self.data = self._collect_data(self.snapshot)
        self.uuid = self._resolve_uuid(self.snapshot)

    def _unwrap(self, snap):
        inner = snap.get("data")
        if isinstance(inner, dict) and any(k in inner for k in _NESTED_MARKERS):
            return self._unwrap(inner)
        if snap.get("credentialSubject"):
            merged = dict(snap)
            merged.update(snap["credentialSubject"])
            return merged
        return snap

    def _collect_data(self, snap):
        if self.raw.get("credentialSubject") or snap.get("evidence"):
            data = {}
            for ev in snap.get("evidence", []):
                op = ev.get("operation")
                if op:
                    data[op] = ev.get("output")
            return data
        return snap.get("data", {}) or {}

    def _resolve_uuid(self, snap):
        return snap.get("uuid") or self.raw.get("uuid")

    # --- command outputs (left raw; parsing is each adapter's job) ---
    @property
    def dmidecode(self):
        return self.data.get("dmidecode")

    @property
    def inxi(self):
        raw = self.data.get("inxi")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                logger.error("inxi not parseable in snapshot %s", self.uuid)
                return None
        return raw

    @property
    def smartctl(self):
        return self.data.get("smartctl") or self.data.get("smart")

    @property
    def lshw(self):
        return self.data.get("lshw")

    @property
    def hwinfo(self):
        return self.data.get("hwinfo")

    @property
    def windows_adapters(self):
        return self.data.get("get-netadapter")

    @property
    def linux_adapters(self):
        return self.data.get("linux-adapters")

    @property
    def device(self):
        return self.snapshot.get("device")

    @property
    def components(self):
        return self.snapshot.get("components", [])

    def has_inxi(self):
        return bool(self.data.get("inxi"))


def detect(sources):
    """Single format dispatch over the already-unwrapped content.

    Order mirrors the historic dispatch in parse.py: lshw/hwinfo before
    'device' (wb11 snapshots never carry lshw), and the credential is no longer
    a branch (once unwrapped it falls into INXI like any regular
    workbench-script snapshot).
    """
    data = sources.data
    if data.get("lshw") or data.get("hwinfo"):
        return LEGACY
    if "device" in sources.snapshot:
        return WB11
    if sources.has_inxi():
        return INXI
    if data.get("dmidecode"):
        return DMI
    return None

import json
import hashlib
import logging

from evidence import legacy_parse
from evidence import old_parse
from evidence import normal_parse, image_processing
from evidence import mobile_parse
from evidence.parse_details import ParseSnapshot

from evidence.models import SystemProperty, UserProperty, RootAlias
from evidence.estimators import estimate_power_on_hours
from evidence.xapian import index
from evidence.normal_parse_details import get_inxi_key, get_inxi
from django.conf import settings

if settings.DPP:
    from dpp.api_dlt import register_device_dlt, register_passport_dlt

logger = logging.getLogger('django')


def get_mac(inxi):
    nets = get_inxi_key(inxi, "Network")
    networks = [(nets[i], nets[i + 1]) for i in range(0, len(nets) - 1, 2)]

    for n, iface in networks:
        if get_inxi(n, "port"):
            return get_inxi(iface, 'mac')

class Build:
    def __init__(self, evidence_json, user, check=False):
        """
        This Build do the save in xapian as document, in Annotations and do
        register in dlt if is configured for that.

        We have 4 cases for parser diferents snapshots than come from workbench.
        1) worbench 11 is old_parse.
        2) legacy is the worbench-script when create a snapshot for devicehub-teal
        3) some snapshots come as a credential. In this case is parsed as normal_parse
        4) normal snapshot from worbench-script is the most basic and is parsed as normal_parse
        """
        self.evidence = evidence_json.copy()
        self.uuid = self.evidence.get('uuid')
        self.user = user

        if evidence_json.get("credentialSubject"):
            self.build = normal_parse.Build(evidence_json)
            self.uuid = evidence_json.get("credentialSubject", {}).get("uuid")
        elif evidence_json.get("data",{}).get("lshw"):
            self.build = legacy_parse.Build(evidence_json)
        elif evidence_json.get("software") == "workbench-android":
            self.build = mobile_parse.Build(evidence_json)
        elif evidence_json.get("software") != "workbench-script":
            self.build = old_parse.Build(evidence_json)
        elif evidence_json.get("data",{}).get("snapshot_type") == "Image":
            self.build = image_processing.Build(evidence_json)
        else:
            self.build = normal_parse.Build(evidence_json)

        if check:
            return

        if not self.build.uuid:
            return

        self.index()
        self.create_annotations()
        self.create_root_alias()
        self.create_mobile_user_properties()
        if settings.DPP:
            self.register_device_dlt()

    def create_root_alias(self):
        """Mirror the custom_id RootAlias pattern (device/forms.py) for the
        operator's manual id, so re-scans collapse to one logical device."""
        manual_id = getattr(self.build, "manual_id", None)
        if not manual_id or not self.user:
            return

        hid = self.build.algorithms.get("ereuse24")
        if not hid:
            return

        alias = "ereuse24:{}".format(hid)
        root = "custom_id:{}".format(manual_id)
        if alias == root:
            return

        # The post_save signal already created a self-referential row for this
        # chid; set_alias re-points it and keeps memberships/cache in sync.
        # Idempotent on re-scans with the same manual id.
        try:
            RootAlias.set_alias(self.user.institution, alias, root, user=self.user)
        except ValueError as err:
            logger.warning("Could not link %s to %s: %s", alias, root, err)

    def create_mobile_user_properties(self):
        """Store derived hardware-test results as per-device UserProperty rows.

        UserProperty is uuid-keyed (unlike SystemProperty, whose value carries
        the identity hash), so these show on the device's Properties tab and are
        aggregated across re-scans without polluting device enumeration. The
        operator can later edit/correct them in the UI.
        """
        if self.evidence.get("software") != "workbench-android":
            return
        if not self.user:
            return

        sibling_uuids = self._device_evidence_uuids()
        chid = next(("{}:{}".format(k, v) for k, v in self.build.algorithms.items()), None)
        device_id = RootAlias.resolve_root(self.user.institution, chid) if chid else None
        data = self.evidence.get("data", {})
        for key, value in self.mobile_annotations(data).items():
            if value in (None, ""):
                continue
            value = str(value)

            # Record value changes vs the device's previous evidences in the
            # device log, so the Properties tab can show only the current value
            # while the history stays visible (time series of re-scans).
            prev = (
                UserProperty.objects.filter(
                    uuid__in=sibling_uuids,
                    owner=self.user.institution,
                    key=key,
                    type=UserProperty.Type.USER,
                )
                .exclude(uuid=self.uuid)
                .order_by("-created")
                .values_list("value", flat=True)
                .first()
            )
            if prev is not None and prev != value:
                self._log_device_event("{}: {} → {}".format(key, prev, value))

            # Current value on the product, so it shows in its Properties tab.
            if device_id:
                UserProperty.objects.update_or_create(
                    owner=self.user.institution,
                    device_id=device_id,
                    key=key,
                    type=UserProperty.Type.USER,
                    defaults={"value": value, "user": self.user},
                )

            exists = UserProperty.objects.filter(
                uuid=self.uuid, owner=self.user.institution, key=key
            ).exists()
            if exists:
                continue
            UserProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                key=key,
                value=value,
                type=UserProperty.Type.USER,
            )

    def _device_evidence_uuids(self):
        """Uuids of every evidence identified as the same device.

        Siblings share an identity SystemProperty value (``algo:hash``), the
        same join used for device enumeration. Includes the current evidence.
        """
        my_values = [
            "{}:{}".format(k, v)
            for k, v in self.build.algorithms.items()
        ]
        if not my_values:
            return [self.uuid]
        uuids = (
            SystemProperty.objects.filter(
                owner=self.user.institution, value__in=my_values
            )
            .values_list("uuid", flat=True)
            .distinct()
        )
        return list(uuids) or [self.uuid]

    def _log_device_event(self, event):
        # Lazy import: action depends on device/evidence, avoid an import cycle.
        from action.models import DeviceLog

        DeviceLog.objects.create(
            institution=self.user.institution,
            user=self.user,
            event=event[:255],
            snapshot_uuid=self.uuid,
        )

    @staticmethod
    def mobile_annotations(data):
        props = {}
        hwtest = data.get("hwtest") or {}
        verdict = hwtest.get("verdict")
        if verdict:
            props["hwtest:verdict"] = verdict
        for result in hwtest.get("results", []):
            rid = result.get("id")
            status = result.get("status")
            if rid and status:
                props["hwtest:{}".format(rid)] = status
            if rid and result.get("note"):
                props["hwtest:{}:note".format(rid)] = result["note"]

        # OS data the obsolescence decision is based on.
        android = data.get("android") or {}
        props["android:version"] = android.get("android_version")
        props["android:api_level"] = android.get("api_level")
        props["android:security_patch"] = android.get("security_patch")

        # Estimate power-on hours from whatever raw wear signals the app shipped.
        estimate = estimate_power_on_hours(data.get("usage") or {})
        if estimate:
            props["usage:power_on_hours"] = estimate.hours
            props["usage:power_on_hours_method"] = estimate.method
            props["usage:power_on_hours_confidence"] = estimate.confidence
        return props

    def index(self):
        snap = json.dumps(self.evidence)
        index(self.user.institution, self.uuid, snap)

    def create_annotations(self):
        prop = SystemProperty.objects.filter(
                uuid=self.uuid,
                owner=self.user.institution,
        )

        if prop:
            txt = "Warning: Snapshot %s already registered (annotation exists)"
            logger.warning(txt, self.uuid)
            return

        for k, v in self.build.algorithms.items():
            value = "{}:{}".format(k, v)
            SystemProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                key=k,
                value=value
            )


    def register_device_dlt(self):
        legacy_dpp = self.build.algorithms.get('ereuse22')
        chid = self.sign(legacy_dpp)
        phid = self.sign(json.dumps(self.build.get_doc()))
        register_device_dlt(chid, phid, self.uuid, self.user)
        register_passport_dlt(chid, phid, self.uuid, self.user)

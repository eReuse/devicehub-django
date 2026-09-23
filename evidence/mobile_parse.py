import logging

from evidence.estimators import estimate_mobile_power_on_hours, get_poh_estimator
from evidence.mixin_parse import BuildMix
from evidence.models import RootAlias, UserProperty


logger = logging.getLogger('django')


class Build(BuildMix):
    """Parser for snapshots produced by workbench-android.

    Android (non-root) cannot read a stable serial or MAC, so identity comes
    from the label id (QR), which the app writes into ``data.device.serial_number``
    (falling back to the per-install UUID). The ``manual_id`` links the evidence
    to its ``custom_id:`` product (see ``link_custom_id``).
    """

    # Snapshot block -> prefix of the product properties derived from it.
    PROPERTY_BLOCKS = {
        "hwtest": "hwtest:",
        "android": "android:",
        "usage": "usage:",
    }

    def has_hardware_data(self, data):
        return bool(data.get("device"))

    def get_details(self):
        device = self.json.get("data", {}).get("device", {})
        self.device = device
        self.manufacturer = device.get("manufacturer", "")
        self.model = device.get("model", "")
        self.chassis = device.get("chassis", "Handheld")
        self.serial_number = device.get("serial_number", "")
        self.type = device.get("type", "Smartphone")
        self.sku = ""
        self.version = ""
        self.mac = ""
        self.manual_id = device.get("manual_id")

    def _get_components(self):
        from evidence.mobile_parse_details import ParseSnapshot

        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components

    def after_save(self, user, uuid):
        self.user = user
        self.evidence_uuid = uuid
        self.link_custom_id()
        self.store_properties()

    def chid(self):
        """The id stored as SystemProperty.value for this evidence."""
        return next(
            ("{}:{}".format(k, v) for k, v in self.algorithms.items()), None
        )

    def link_custom_id(self):
        """Link this evidence's chid to the ``custom_id:`` product of its label,
        like the Custom ID of device/forms.py, so all scans of a phone (and its
        DH-scan record) are one product. Idempotent on re-scans."""
        chid = self.chid()
        if not self.manual_id or not chid:
            return

        try:
            RootAlias.set_alias(
                self.user.institution,
                chid,
                "custom_id:{}".format(self.manual_id),
                user=self.user,
            )
        except ValueError as err:
            logger.warning("Could not link %s to custom_id:%s: %s", chid, self.manual_id, err)

    def store_properties(self):
        """Store hardware-test results, OS data and usage estimation as
        UserProperty rows of the product, so they show on its Properties tab.

        Changes against the product's previous values are written to the
        device log. Values of a block that the snapshot carries but no longer
        reports are removed.
        """
        chid = self.chid()
        if not chid:
            return

        owner = self.user.institution
        device_id = RootAlias.resolve_root(owner, chid)
        data = self.json.get("data", {})
        annotations = {
            key: str(value)
            for key, value in self.annotations(data).items()
            if value not in (None, "")
        }
        current = {
            p.key: p
            for p in UserProperty.objects.filter(
                owner=owner,
                device_id=device_id,
                type=UserProperty.Type.USER,
            )
        }

        for block, prefix in self.PROPERTY_BLOCKS.items():
            if block not in data:
                continue
            for key, prop in current.items():
                if key.startswith(prefix) and key not in annotations:
                    self.log("{}: {} → (removed)".format(key, prop.value))
                    prop.delete()

        for key, value in annotations.items():
            prop = current.get(key)
            if prop is None:
                UserProperty.objects.create(
                    owner=owner,
                    device_id=device_id,
                    key=key,
                    value=value,
                    user=self.user,
                    type=UserProperty.Type.USER,
                )
                continue
            if prop.value != value:
                self.log("{}: {} → {}".format(key, prop.value, value))
                prop.value = value
                prop.user = self.user
                prop.save()

    def log(self, event):
        # Lazy import: action depends on device/evidence, avoid an import cycle.
        from action.models import DeviceLog

        DeviceLog.objects.create(
            institution=self.user.institution,
            user=self.user,
            event=event[:255],
            snapshot_uuid=self.evidence_uuid,
        )

    @staticmethod
    def annotations(data):
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

        props.update(Build.usage_annotations(data))
        return props

    @staticmethod
    def usage_annotations(data, estimator=None):
        """Power-on hours estimated from the raw signals the app shipped, with
        the configured estimator implementation (see evidence/estimators.py)."""
        estimator = estimator or get_poh_estimator()
        estimate = estimate_mobile_power_on_hours(data, estimator)
        if not estimate:
            return {}
        return {
            "usage:power_on_hours": estimate.hours,
            "usage:power_on_hours_method": estimate.method,
            "usage:power_on_hours_confidence": estimate.confidence,
            "usage:power_on_hours_estimator": estimator.name,
        }

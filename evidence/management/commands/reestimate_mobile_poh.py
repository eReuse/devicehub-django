import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from action.models import DeviceLog
from device.models import Device
from evidence.estimators import get_poh_estimator
from evidence.mobile_parse import Build
from evidence.models import UserProperty
from utils.constants import WORKBENCH_ANDROID


logger = logging.getLogger('django')


class Command(BaseCommand):
    help = (
        "Recompute the usage:power_on_hours* properties of every mobile product "
        "from its latest workbench-android evidence, with the configured "
        "estimator (settings.MOBILE_POH_ESTIMATOR) or --estimator."
    )

    def add_arguments(self, parser):
        parser.add_argument("--estimator", default=None, help="registered estimator name")
        parser.add_argument("--dry-run", action="store_true", help="print changes without saving")

    def handle(self, *args, **options):
        estimator = get_poh_estimator(options["estimator"])
        dry_run = options["dry_run"]

        products = (
            UserProperty.objects.filter(type=UserProperty.Type.USER, device_id__isnull=False)
            .filter(Q(key__startswith="hwtest:") | Q(key__startswith="android:"))
            .values_list("owner", "device_id")
            .distinct()
        )
        changed = 0
        for owner_id, device_id in products:
            prop = UserProperty.objects.filter(owner_id=owner_id, device_id=device_id).first()
            evidence = self.last_mobile_evidence(device_id, prop.owner)
            if evidence is None:
                continue
            new = {
                k: str(v)
                for k, v in Build.usage_annotations(evidence.doc.get("data") or {}, estimator).items()
            }
            changed += self.apply(prop.owner, device_id, evidence.uuid, new, dry_run)

        verb = "Would change" if dry_run else "Changed"
        self.stdout.write("{} {} properties with estimator {}".format(verb, changed, estimator.name))

    @staticmethod
    def last_mobile_evidence(device_id, owner):
        device = Device(id=device_id, owner=owner)
        device.get_evidences()
        for evidence in reversed(device.evidences):
            evidence.get_doc()
            if (evidence.doc or {}).get("software") == WORKBENCH_ANDROID:
                return evidence
        return None

    def apply(self, owner, device_id, snapshot_uuid, new, dry_run):
        current = {
            p.key: p
            for p in UserProperty.objects.filter(
                owner=owner,
                device_id=device_id,
                type=UserProperty.Type.USER,
                key__startswith="usage:power_on_hours",
            )
        }
        events = []
        for key, prop in current.items():
            if key not in new:
                events.append("{}: {} → (removed)".format(key, prop.value))
                if not dry_run:
                    prop.delete()
        for key, value in new.items():
            prop = current.get(key)
            if prop is not None and prop.value == value:
                continue
            events.append("{}: {} → {}".format(key, prop.value if prop else "(none)", value))
            if dry_run:
                continue
            if prop is None:
                UserProperty.objects.create(
                    owner=owner, device_id=device_id, key=key, value=value,
                    type=UserProperty.Type.USER,
                )
            else:
                prop.value = value
                prop.save()

        for event in events:
            self.stdout.write("{} {}".format(device_id, event))
            if not dry_run:
                DeviceLog.objects.create(
                    institution=owner, event=event[:255], snapshot_uuid=snapshot_uuid,
                )
        return len(events)

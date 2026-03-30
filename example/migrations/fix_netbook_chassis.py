"""
Fix non-normalised laptop chassis values in SystemProperty and RootAlias.

Problem: old_parse (Workbench 11) stores the raw chassis string from the
snapshot (e.g. "Netbook", "notebook", "sub-notebook", "portable", …) instead
of the canonical "Laptop" value that normal_parse produces via inxi.
Because the chassis string is part of the HID that gets hashed, the same
physical device ends up with different SHA3-256 hashes and duplicate identities.

This script normalises every chassis value that CHASSIS_DH maps to "Laptop"
but that is not already the string "Laptop":
    portable, laptop, notebook, sub-notebook, netbook  →  Laptop

Steps for each UUID:
1. Finds all SystemProperty entries for an institution.
2. Looks up the snapshot in Xapian.
3. Checks if it is an old_parse snapshot.
4. Checks if the stored chassis maps to "Laptop" but is not already "Laptop".
5. Verifies the stored hash matches the recalculated raw-chassis hash (sanity).
6. Recomputes the hash with chassis="Laptop".
7. Updates SystemProperty.value with the new hash.
8. Updates any RootAlias entries that pointed to the old value.

Usage:
    python fix_netbook_chassis.py --email admin@example.org
    python fix_netbook_chassis.py --email admin@example.org --dry-run
"""

import os
import json
import hashlib
import logging
import argparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhub.settings')

import django
django.setup()

from django.contrib.auth import get_user_model

from evidence.models import SystemProperty, RootAlias
from evidence.xapian import search
from evidence.legacy_parse import get_mac
from utils.constants import ALGOS, CHASSIS_DH


logger = logging.getLogger(__name__)
User = get_user_model()

NEW_CHASSIS = "Laptop"
# All raw values that CHASSIS_DH maps to "Laptop" but are not already "Laptop"
LAPTOP_ALIASES = CHASSIS_DH.get("Laptop", set()) - {"laptop"}


def needs_normalisation(chassis):
    """Return True if chassis maps to Laptop but is not the canonical form."""
    return chassis.lower() in LAPTOP_ALIASES


def is_old_parse(snapshot):
    """Return True if snapshot was parsed with old_parse (Workbench 11)."""
    if snapshot.get("credentialSubject"):
        return False
    if snapshot.get("data", {}).get("lshw"):
        return False
    return snapshot.get("software") != "workbench-script"


def get_snapshot_from_xapian(institution, uuid):
    qry = 'uuid:"{}"'.format(uuid)
    matches = search(institution, qry, limit=1)
    if not matches:
        return None
    for xa in matches:
        return json.loads(xa.document.get_data())
    return None


def get_fields_from_old_parse(snapshot):
    """Extract HID fields from an old_parse snapshot."""
    device = snapshot.get("device", {})

    mac = ""
    lshw = snapshot.get("debug", {}).get("lshw")
    if lshw:
        mac = get_mac(lshw) or ""

    return {
        "manufacturer": device.get("manufacturer", '') or '',
        "model": device.get("model", '') or '',
        "chassis": device.get("chassis", '') or '',
        "serial_number": device.get("serialNumber", '') or '',
        "sku": device.get("sku", '') or '',
        "type": device.get("type", '') or '',
        "version": device.get("version", '') or '',
        "mac": mac,
    }


def build_hid(fields, algo):
    """Concatenate HID fields in the order defined by the algorithm."""
    return "".join(fields.get(f, '') or '' for f in ALGOS.get(algo, []))


def sign(hid):
    return hashlib.sha3_256(hid.encode()).hexdigest()


def fix_netbook_chassis(institution, dry_run=False):
    uuids = (
        SystemProperty.objects
        .filter(owner=institution)
        .values_list('uuid', flat=True)
        .distinct()
    )

    total = fixed = skipped = errors = 0

    for uuid in uuids:
        total += 1
        try:
            snapshot = get_snapshot_from_xapian(institution, uuid)
            if not snapshot:
                logger.warning("No snapshot in Xapian for UUID: %s", uuid)
                skipped += 1
                continue

            if not is_old_parse(snapshot):
                continue

            fields = get_fields_from_old_parse(snapshot)
            if not needs_normalisation(fields["chassis"]):
                continue

            logger.info(
                "Non-normalised chassis '%s' found — UUID: %s",
                fields["chassis"], uuid,
            )

            props = SystemProperty.objects.filter(uuid=uuid, owner=institution)

            for sp in props:
                algo = sp.key
                if algo not in ALGOS:
                    logger.warning("  Unknown algo '%s' for UUID %s — skipping", algo, uuid)
                    skipped += 1
                    continue

                # Sanity check: recalculate with Netbook and compare
                old_hid = build_hid(fields, algo)
                old_hash = sign(old_hid)
                expected_value = "{}:{}".format(algo, old_hash)

                if sp.value != expected_value:
                    logger.warning(
                        "  [%s] UUID %s: stored value does not match recalculated hash.\n"
                        "    stored  : %s\n"
                        "    expected: %s",
                        algo, uuid, sp.value, expected_value,
                    )
                    skipped += 1
                    continue

                # Build new hash with Laptop
                new_fields = dict(fields, chassis=NEW_CHASSIS)
                new_hid = build_hid(new_fields, algo)
                new_value = "{}:{}".format(algo, sign(new_hid))
                old_value = sp.value

                # Find all RootAlias entries pointing to the old value
                aliases = RootAlias.objects.filter(owner=institution, alias=old_value)

                logger.info(
                    "  [%s] %s -> %s  (RootAlias entries: %d)",
                    algo, old_value, new_value, aliases.count(),
                )

                if not dry_run:
                    sp.value = new_value
                    sp.save()

                for alias_obj in aliases:
                    existing = RootAlias.objects.filter(
                        owner=institution,
                        alias=new_value,
                    ).exclude(pk=alias_obj.pk).first()

                    if existing:
                        if existing.root == alias_obj.root:
                            logger.info(
                                "  RootAlias '%s' already exists with same root '%s'"
                                " — deleting old Netbook alias",
                                new_value, existing.root,
                            )
                            if not dry_run:
                                alias_obj.delete()
                        else:
                            logger.warning(
                                "  RootAlias '%s' already exists with DIFFERENT root"
                                " (existing: '%s', old: '%s') — skipping alias update",
                                new_value, existing.root, alias_obj.root,
                            )
                    else:
                        logger.info(
                            "  RootAlias: '%s' -> '%s'",
                            alias_obj.alias, new_value,
                        )
                        if not dry_run:
                            alias_obj.alias = new_value
                            alias_obj.save()

                fixed += 1

        except Exception as err:
            logger.error("Error processing UUID %s: %s", uuid, err)
            errors += 1

    logger.info(
        "Done. Checked: %d | Fixed props: %d | Skipped: %d | Errors: %d",
        total, fixed, skipped, errors,
    )


def prepare_logger():
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter('[%(asctime)s] fix_netbook: %(levelname)s: %(message)s')
    )
    logger.addHandler(handler)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fix Netbook->Laptop chassis in SystemProperty and RootAlias."
    )
    parser.add_argument(
        '--email', required=True,
        help="Email of a user belonging to the target institution.",
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Print planned changes without saving anything.",
    )
    return parser.parse_args()


def main():
    prepare_logger()
    args = parse_args()

    user = User.objects.get(email=args.email)
    institution = user.institution

    logger.info("START — institution: %s | dry_run: %s", institution, args.dry_run)
    if args.dry_run:
        logger.info("DRY RUN — no changes will be written")

    fix_netbook_chassis(institution, dry_run=args.dry_run)
    logger.info("END")


if __name__ == '__main__':
    main()

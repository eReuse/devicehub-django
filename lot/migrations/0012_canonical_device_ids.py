from django.db import migrations


def _alias_to_root_map(RootAlias):
    """Build {(owner_id, alias): root} dict from the RootAlias table."""
    mapping = {}
    for row in RootAlias.objects.values("owner_id", "alias", "root").iterator():
        mapping[(row["owner_id"], row["alias"])] = row["root"]
    return mapping


def resolve_device_ids_to_root(apps, schema_editor):
    """rewrite DeviceLot.device_id and DeviceBeneficiary.device_id
    to the canonical root for each institution, and deduplicate collisions.

    Every SystemProperty.value has a RootAlias row whose root
    is the canonical id (self-ref or user-chosen). This migration uses that
    table to replace any physical id stored in DeviceLot/DeviceBeneficiary
    with its canonical root, merging duplicates that collapse together.
    """
    RootAlias = apps.get_model("evidence", "RootAlias")
    DeviceLot = apps.get_model("lot", "DeviceLot")
    DeviceBeneficiary = apps.get_model("lot", "DeviceBeneficiary")

    alias_to_root = _alias_to_root_map(RootAlias)

    # --- DeviceLot ---------------------------------------------------------
    # Iterate with select_related to access lot.owner_id cheaply.
    seen_keys = set()
    to_delete_dl = []
    to_update_dl = []

    dl_qs = DeviceLot.objects.select_related("lot").order_by("pk").iterator()
    for dl in dl_qs:
        owner_id = dl.lot.owner_id
        root = alias_to_root.get((owner_id, dl.device_id), dl.device_id)
        key = (dl.lot_id, root)
        if key in seen_keys:
            to_delete_dl.append(dl.pk)
            continue
        seen_keys.add(key)
        if root != dl.device_id:
            dl.device_id = root
            to_update_dl.append(dl)

    if to_delete_dl:
        DeviceLot.objects.filter(pk__in=to_delete_dl).delete()
    # bulk_update in chunks to avoid huge parameter lists
    for i in range(0, len(to_update_dl), 500):
        DeviceLot.objects.bulk_update(
            to_update_dl[i:i + 500], ["device_id"]
        )

    # --- DeviceBeneficiary -------------------------------------------------
    # Dedup per (beneficiary_id, root); each beneficiary keeps at most one
    # row per canonical device.
    seen_keys = set()
    to_delete_db = []
    to_update_db = []

    db_qs = (
        DeviceBeneficiary.objects
        .select_related("beneficiary__lot")
        .order_by("pk")
        .iterator()
    )
    for db in db_qs:
        owner_id = db.beneficiary.lot.owner_id
        root = alias_to_root.get((owner_id, db.device_id), db.device_id)
        key = (db.beneficiary_id, root)
        if key in seen_keys:
            to_delete_db.append(db.pk)
            continue
        seen_keys.add(key)
        if root != db.device_id:
            db.device_id = root
            to_update_db.append(db)

    if to_delete_db:
        DeviceBeneficiary.objects.filter(pk__in=to_delete_db).delete()
    for i in range(0, len(to_update_db), 500):
        DeviceBeneficiary.objects.bulk_update(
            to_update_db[i:i + 500], ["device_id"]
        )


def noop_reverse(apps, schema_editor):
    """Reverse is not meaningful: we cannot recover which physical alias a
    row originally pointed to after collapsing. Deduplicated rows are lost.
    This no-op keeps `migrate <prev>` possible without erroring out.
    """
    return


class Migration(migrations.Migration):

    dependencies = [
        ("lot", "0011_beneficiary_devicebeneficiary_donor_lotsubscription_and_more"),
        ("evidence", "0008_rootalias_self_reference_backfill"),
    ]

    operations = [
        migrations.RunPython(
            resolve_device_ids_to_root,
            reverse_code=noop_reverse,
        ),
    ]

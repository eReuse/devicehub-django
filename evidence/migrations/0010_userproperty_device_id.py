import logging

from django.db import migrations, models
from django.db.models import Q


logger = logging.getLogger(__name__)


def populate_device_id(apps, schema_editor):
    """For each UserProperty(type=USER) resolve device_id from RootAlias.

    Steps:
    1. Find the SystemProperty row matching the UserProperty.uuid to get
       the physical value and owner.
    2. Resolve that value to its canonical root via RootAlias.
    3. Deduplicate before writing: for each (key, resolved_root, owner) group
       keep only the most recent row (newest-first); delete the older ones
       before issuing any UPDATE so the unique constraint is never violated.
    4. Bulk-update device_id on surviving rows; leave uuid unchanged
       (option B: kept for auditability).

    ERASE_SERVER rows are left untouched.
    """
    UserProperty = apps.get_model("evidence", "UserProperty")
    SystemProperty = apps.get_model("evidence", "SystemProperty")
    RootAlias = apps.get_model("evidence", "RootAlias")

    USER = 1

    # Build lookup: uuid -> (value, owner_id) from SystemProperty
    uuid_to_sp = {
        str(row["uuid"]): (row["value"], row["owner_id"])
        for row in SystemProperty.objects.values("uuid", "value", "owner_id")
    }

    # Build lookup: (owner_id, alias) -> root from RootAlias
    alias_to_root = {
        (row["owner_id"], row["alias"]): row["root"]
        for row in RootAlias.objects.values("owner_id", "alias", "root")
    }

    orphans = 0
    # pk -> resolved device_id for all rows that survived deduplication
    pk_to_device_id = {}
    # Process newest-first so the first entry per (key, root, owner) wins.
    seen = {}   # (key, root, owner_id) -> pk already claimed

    # Materialise all rows before iterating to avoid cursor-shift issues on
    # SQLite when rows are deleted mid-iteration (iterator() uses LIMIT/OFFSET).
    rows = list(
        UserProperty.objects
        .filter(type=USER)
        .order_by("-created", "-pk")
        .values("pk", "uuid", "key", "owner_id")
    )
    for row in rows:
        sp_key = str(row["uuid"]) if row["uuid"] else None
        if not sp_key or sp_key not in uuid_to_sp:
            orphans += 1
            logger.warning(
                "UserProperty pk=%s has uuid=%s with no matching SystemProperty; skipping",
                row["pk"], row["uuid"],
            )
            continue

        value, owner_id = uuid_to_sp[sp_key]
        root = alias_to_root.get((owner_id, value), value)
        group = (row["key"], root, owner_id)

        if group in seen:
            # Older duplicate: delete before any UPDATE to avoid constraint violation.
            UserProperty.objects.filter(pk=row["pk"]).delete()
            continue

        seen[group] = row["pk"]
        pk_to_device_id[row["pk"]] = root

    if orphans:
        logger.warning("%d UserProperty(USER) rows had no matching SystemProperty", orphans)

    # Bulk-update surviving rows. No duplicates remain so no constraint risk.
    to_update = []
    for up in UserProperty.objects.filter(pk__in=list(pk_to_device_id)).iterator(chunk_size=500):
        up.device_id = pk_to_device_id[up.pk]
        to_update.append(up)

    if to_update:
        UserProperty.objects.bulk_update(to_update, ["device_id"], batch_size=500)
        logger.info(
            "Populated device_id for %d UserProperty(USER) rows", len(to_update)
        )


def noop_reverse(apps, schema_editor):
    # Forward migration sets device_id and deduplicates rows; reversal would
    # require the original uuid mapping which is preserved (option B) but
    # restoring exact pre-migration state is not implemented here.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0009_rootalias_updated"),
    ]

    operations = [
        # (a) Make uuid nullable for UserProperty (ERASE_SERVER still uses it;
        #     USER rows will have it set to NULL after the data migration if
        #     desired, but option B keeps it for auditability).
        migrations.AlterField(
            model_name="userproperty",
            name="uuid",
            field=models.UUIDField(null=True, blank=True),
        ),
        # (b) Add device_id field.
        migrations.AddField(
            model_name="userproperty",
            name="device_id",
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        # (c) Drop the old unconditional unique constraint.
        migrations.RemoveConstraint(
            model_name="userproperty",
            name="userproperty_unique_type_key_uuid",
        ),
        # (d) Add the two new conditional unique constraints.
        migrations.AddConstraint(
            model_name="userproperty",
            constraint=models.UniqueConstraint(
                fields=["key", "device_id", "owner"],
                condition=Q(type=1),
                name="userproperty_unique_user_key_device_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="userproperty",
            constraint=models.UniqueConstraint(
                fields=["key", "uuid"],
                condition=Q(type=2),
                name="userproperty_unique_eraseserver_key_uuid",
            ),
        ),
        # (e) Add covering index for the new read path.
        migrations.AddIndex(
            model_name="userproperty",
            index=models.Index(
                fields=["owner", "device_id"],
                name="userproperty_owner_device_idx",
            ),
        ),
        # (f) Data migration: populate device_id for all type=USER rows.
        migrations.RunPython(populate_device_id, reverse_code=noop_reverse),
    ]

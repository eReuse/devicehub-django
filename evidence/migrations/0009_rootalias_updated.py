from django.db import migrations, models
from django.db.models import Max, Min


def backfill_updated(apps, schema_editor):
    """Populate ``RootAlias.updated`` (and refresh ``created``) from
    SystemProperty aggregates so existing rows match the new invariant:
    ``created = MIN(sp.created)``, ``updated = MAX(sp.created)`` over all
    SystemProperty rows with the same ``(owner, value=alias)``.

    Aliases without a matching SystemProperty (rare) fall back to their
    current ``created`` value for ``updated`` and leave ``created`` as-is.
    """
    SystemProperty = apps.get_model("evidence", "SystemProperty")
    RootAlias = apps.get_model("evidence", "RootAlias")

    agg = {
        (r["owner_id"], r["value"]): (r["min_c"], r["max_c"])
        for r in SystemProperty.objects.values("owner_id", "value")
            .annotate(min_c=Min("created"), max_c=Max("created"))
    }

    batch = []
    for row in RootAlias.objects.iterator(chunk_size=1000):
        pair = agg.get((row.owner_id, row.alias))
        if pair:
            row.created, row.updated = pair
        else:
            row.updated = row.created
        batch.append(row)
        if len(batch) >= 1000:
            RootAlias.objects.bulk_update(batch, ["created", "updated"])
            batch = []
    if batch:
        RootAlias.objects.bulk_update(batch, ["created", "updated"])


def noop_reverse(apps, schema_editor):
    # Reverse cannot recover original timestamps; schema-level reversal
    # is handled by the surrounding AlterField/RemoveField operations.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0008_rootalias_self_reference_backfill"),
    ]

    operations = [
        # (a) Schema: make ``created`` nullable (remove auto_now_add so the
        # backfill can overwrite it) and add nullable ``updated``.
        migrations.AlterField(
            model_name="rootalias",
            name="created",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="rootalias",
            name="updated",
            field=models.DateTimeField(null=True),
        ),
        # (b) Data migration: backfill both columns from SystemProperty.
        migrations.RunPython(backfill_updated, reverse_code=noop_reverse),
        # (c) Schema final: make both NOT NULL and add the covering index.
        migrations.AlterField(
            model_name="rootalias",
            name="created",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="rootalias",
            name="updated",
            field=models.DateTimeField(),
        ),
        migrations.AddIndex(
            model_name="rootalias",
            index=models.Index(
                fields=["owner", "updated"],
                name="evidence_ro_owner_upd_idx",
            ),
        ),
    ]

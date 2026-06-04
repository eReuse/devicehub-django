from django.db import migrations


def create_self_reference_aliases(apps, schema_editor):
    """Backfill RootAlias with one self-reference entry per (owner, value)
    found in SystemProperty. This makes RootAlias the canonical catalog of
    all existing devices (Option 5).

    An entry (owner=O, alias=X, root=X) is created for every distinct
    SystemProperty.value X that does not already have a RootAlias row with
    the same (owner, alias).
    """
    SystemProperty = apps.get_model("evidence", "SystemProperty")
    RootAlias = apps.get_model("evidence", "RootAlias")

    existing = set(
        RootAlias.objects.values_list("owner_id", "alias")
    )

    seen = set()
    to_create = []
    qs = SystemProperty.objects.values(
        "owner_id", "user_id", "value"
    ).iterator()
    for row in qs:
        key = (row["owner_id"], row["value"])
        if key in seen or key in existing:
            continue
        seen.add(key)
        to_create.append(
            RootAlias(
                owner_id=row["owner_id"],
                user_id=row["user_id"],
                alias=row["value"],
                root=row["value"],
            )
        )

    if to_create:
        RootAlias.objects.bulk_create(to_create, batch_size=500)


def remove_self_reference_aliases(apps, schema_editor):
    """Reverse migration: drop rows where alias == root.

    Non self-referential entries (genuine aliases) are kept.
    """
    RootAlias = apps.get_model("evidence", "RootAlias")
    # F-expression comparison avoids loading rows in Python
    from django.db.models import F
    RootAlias.objects.filter(alias=F("root")).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0007_rootalias_rootalias_rootalias_unique"),
    ]

    operations = [
        migrations.RunPython(
            create_self_reference_aliases,
            reverse_code=remove_self_reference_aliases,
        ),
    ]

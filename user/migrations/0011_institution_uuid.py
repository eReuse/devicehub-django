import uuid

from django.db import migrations, models


def assign_uuids(apps, schema_editor):
    Institution = apps.get_model("user", "Institution")
    for institution in Institution.objects.filter(uuid__isnull=True):
        institution.uuid = uuid.uuid4()
        institution.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0010_alter_institution_facility_id_uri"),
    ]

    operations = [
        migrations.AddField(
            model_name="institution",
            name="uuid",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(assign_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="institution",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]

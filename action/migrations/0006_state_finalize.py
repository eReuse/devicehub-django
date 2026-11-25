# State redesign, step 3/3: drop the legacy columns, make the new ones
# mandatory and enforce one row per (institution, root).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("action", "0005_state_migrate_data"),
        ("user", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="state",
            name="snapshot_uuid",
        ),
        migrations.RemoveField(
            model_name="state",
            name="state",
        ),
        migrations.AlterField(
            model_name="state",
            name="institution",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="user.institution",
            ),
        ),
        migrations.AlterField(
            model_name="state",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="state",
            name="root",
            field=models.CharField(max_length=256),
        ),
        migrations.AlterField(
            model_name="state",
            name="state_definition",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="states",
                to="action.statedefinition",
            ),
        ),
        migrations.AddConstraint(
            model_name="state",
            constraint=models.UniqueConstraint(
                fields=("institution", "root"),
                name="state_unique_institution_root",
            ),
        ),
    ]

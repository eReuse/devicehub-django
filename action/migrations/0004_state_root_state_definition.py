# State redesign, step 1/3: add the new columns as nullable so the data
# migration (0005) can fill them from the legacy snapshot_uuid/state ones.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("action", "0003_statedefinition_auto_issue_dte_and_more"),
    ]

    operations = [
        # Legacy columns become nullable so 0005 can insert the new rows
        # next to the old ones; 0006 drops them.
        migrations.AlterField(
            model_name="state",
            name="snapshot_uuid",
            field=models.UUIDField(null=True),
        ),
        migrations.AlterField(
            model_name="state",
            name="state",
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="state",
            name="date",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="state",
            name="root",
            field=models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="state",
            name="state_definition",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="states",
                to="action.statedefinition",
            ),
        ),
    ]

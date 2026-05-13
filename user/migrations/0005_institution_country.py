from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0004_alter_institution_algorithm"),
    ]

    operations = [
        migrations.AddField(
            model_name="institution",
            name="country",
            field=models.CharField(
                blank=True,
                max_length=2,
                null=True,
                verbose_name="Country",
            ),
        ),
    ]

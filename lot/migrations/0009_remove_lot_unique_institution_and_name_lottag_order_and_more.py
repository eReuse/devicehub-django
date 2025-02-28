# Generated by Django 5.0.6 on 2025-02-28 16:57

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lot", "0008_lot_unique_institution_and_name"),
        ("user", "0002_institution_algorithm"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="lot",
            name="unique_institution_and_name",
        ),
        migrations.AddField(
            model_name="lottag",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="lot",
            constraint=models.UniqueConstraint(
                fields=("owner", "name", "type"), name="unique_institution_and_name"
            ),
        ),
    ]

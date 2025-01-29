# Generated by Django 5.0.6 on 2025-01-29 11:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lot", "0004_remove_lotproperty_lot_unique_type_key_lot_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lotproperty",
            name="type",
            field=models.SmallIntegerField(
                choices=[(0, "System"), (1, "User")], default=1
            ),
        ),
    ]

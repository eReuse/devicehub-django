# Generated by Django 5.0.6 on 2024-12-18 12:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lot", "0003_lotproperty_delete_lotannotation_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="lotproperty",
            name="lot_unique_type_key_lot",
        ),
        migrations.AlterField(
            model_name="lotproperty",
            name="type",
            field=models.SmallIntegerField(
                choices=[(0, "System"), (1, "User"), (2, "Document")], default=1
            ),
        ),
    ]
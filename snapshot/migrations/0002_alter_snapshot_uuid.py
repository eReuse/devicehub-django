# Generated by Django 5.0.6 on 2024-07-11 14:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("snapshot", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="snapshot",
            name="uuid",
            field=models.UUIDField(unique=True),
        ),
    ]

# Generated by Django 5.0.6 on 2024-12-18 12:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0003_systemproperty_userproperty_delete_annotation_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="userproperty",
            name="user_unique_type_key_uuid",
        ),
    ]

# Generated by Django 5.0.6 on 2024-12-10 19:37

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0002_alter_annotation_type"),
        ("user", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemProperty",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("key", models.CharField(max_length=256)),
                ("value", models.CharField(max_length=256)),
                ("uuid", models.UUIDField()),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="user.institution",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserProperty",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("key", models.CharField(max_length=256)),
                ("value", models.CharField(max_length=256)),
                ("uuid", models.UUIDField()),
                (
                    "type",
                    models.SmallIntegerField(
                        choices=[(1, "User"), (2, "Document"), (3, "EraseServer")],
                        default=1,
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="user.institution",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="Annotation",
        ),
        migrations.AddConstraint(
            model_name="systemproperty",
            constraint=models.UniqueConstraint(
                fields=("key", "uuid"), name="system_unique_type_key_uuid"
            ),
        ),
        migrations.AddConstraint(
            model_name="userproperty",
            constraint=models.UniqueConstraint(
                fields=("key", "uuid", "type"), name="user_unique_type_key_uuid"
            ),
        ),
    ]

# Generated by Django 5.0.6 on 2024-07-03 12:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("device", "0002_alter_device_brand_alter_device_devicehub_id_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="component",
            name="type",
        ),
        migrations.RemoveField(
            model_name="computer",
            name="type",
        ),
        migrations.RemoveField(
            model_name="datastorage",
            name="type",
        ),
        migrations.AlterField(
            model_name="computer",
            name="chassis",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Tower", "Tower"),
                    ("All in one", "Allinone"),
                    ("Microtower", "Microtower"),
                    ("Netbook", "Netbook"),
                    ("Laptop", "Laptop"),
                    ("Tablet", "Tabler"),
                    ("Server", "Server"),
                    ("Non-physical device", "Virtual"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="computer",
            name="sku",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name="device",
            name="type",
            field=models.CharField(
                choices=[
                    ("Desktop", "Desktop"),
                    ("Laptop", "Laptop"),
                    ("Server", "Server"),
                    ("GraphicCard", "Graphiccard"),
                    ("HardDrive", "Harddrive"),
                    ("SolidStateDrive", "Solidstatedrive"),
                    ("Motherboard", "Motherboard"),
                    ("NetworkAdapter", "Networkadapter"),
                    ("Processor", "Processor"),
                    ("RamModule", "Rammodule"),
                    ("SoundCard", "Soundcard"),
                    ("Display", "Display"),
                    ("Battery", "Battery"),
                    ("Camera", "Camera"),
                ],
                default="Laptop",
                max_length=32,
            ),
        ),
    ]

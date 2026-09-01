from django.db import migrations


SEED_ATTRIBUTES = {'Desktop': ['model', 'manufacturer', 'cpu_model', 'ram_total', 'storage', 'gpu_model'],
 'Laptop': ['model',
            'manufacturer',
            'cpu_model',
            'ram_total',
            'storage',
            'screen_size',
            'battery_health'],
 'Server': ['model',
            'manufacturer',
            'cpu_model',
            'ram_total',
            'storage',
            'raid_controller',
            'power_supply'],
 'GraphicCard': ['model', 'manufacturer', 'vram_capacity', 'vram_type', 'core_clock'],
 'HardDrive': ['model', 'manufacturer', 'capacity', 'interface', 'rpm'],
 'SolidStateDrive': ['model', 'manufacturer', 'capacity', 'interface', 'health_tbw'],
 'Motherboard': ['model', 'manufacturer', 'socket_type', 'chipset', 'ram_slots'],
 'NetworkAdapter': ['model', 'manufacturer', 'speed', 'port_type'],
 'Processor': ['model', 'manufacturer', 'cpu_cores', 'base_clock', 'socket_type'],
 'RamModule': ['model', 'manufacturer', 'ram_type', 'capacity', 'speed_mhz'],
 'SoundCard': ['model', 'manufacturer', 'channels', 'interface'],
 'Display': ['model', 'manufacturer', 'resolution', 'refresh_rate', 'panel_type'],
 'Battery': ['model', 'manufacturer', 'capacity_wh', 'cycle_count'],
 'Camera': ['model', 'manufacturer', 'megapixels', 'max_resolution'],
 'Switch': ['model',
            'manufacturer',
            'ports',
            'link_speed',
            'poe_budget',
            'management_type'],
 'Router': ['model', 'manufacturer', 'ports', 'throughput', 'routing_protocols'],
 'RouterWifi': ['model',
                'manufacturer',
                'wifi_standard',
                'frequency_bands',
                'antennas']}


def seed_attributes(apps, schema_editor):
    DeviceType = apps.get_model("device", "DeviceType")
    DeviceTypeAttribute = apps.get_model("device", "DeviceTypeAttribute")

    for type_name, attribute_names in SEED_ATTRIBUTES.items():
        for device_type in DeviceType.objects.filter(name__iexact=type_name):
            DeviceTypeAttribute.objects.bulk_create(
                [
                    DeviceTypeAttribute(
                        device_type=device_type,
                        name=attribute_name,
                        order=order,
                    )
                    for order, attribute_name in enumerate(attribute_names, start=1)
                ]
            )


def unseed_attributes(apps, schema_editor):
    DeviceTypeAttribute = apps.get_model("device", "DeviceTypeAttribute")

    for type_name, attribute_names in SEED_ATTRIBUTES.items():
        DeviceTypeAttribute.objects.filter(
            device_type__name__iexact=type_name,
            name__in=attribute_names,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("device", "0003_devicetype_icon_devicetype_label_devicetypeattribute_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_attributes, unseed_attributes),
    ]

from django.db import migrations


def update_status_values(apps, schema_editor):
    DeviceBeneficiary = apps.get_model('lot', 'DeviceBeneficiary')
    # Update in reverse order to avoid overwriting values mid-migration
    DeviceBeneficiary.objects.filter(status=4).update(status=5)  # RETURNED: 4 -> 5
    DeviceBeneficiary.objects.filter(status=3).update(status=4)  # DELIVERED: 3 -> 4
    DeviceBeneficiary.objects.filter(status=2).update(status=3)  # CONFIRMED: 2 -> 3


def reverse_status_values(apps, schema_editor):
    DeviceBeneficiary = apps.get_model('lot', 'DeviceBeneficiary')
    DeviceBeneficiary.objects.filter(status=3).update(status=2)  # CONFIRMED: 3 -> 2
    DeviceBeneficiary.objects.filter(status=4).update(status=3)  # DELIVERED: 4 -> 3
    DeviceBeneficiary.objects.filter(status=5).update(status=4)  # RETURNED: 5 -> 4


class Migration(migrations.Migration):

    dependencies = [
        ('lot', '0011_beneficiary_devicebeneficiary_donor_lotsubscription_and_more'),
    ]

    operations = [
        migrations.RunPython(update_status_values, reverse_status_values),
    ]

# Generated by Django 5.0.6 on 2025-02-18 08:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='institution',
            name='algorithm',
            field=models.CharField(choices=[('ereuse24', 'ereuse24'), ('ereuse22', 'ereuse22')], default='ereuse24', max_length=30),
        ),
    ]

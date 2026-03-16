from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('user', '0003_user_is_circuit_manager_user_is_shop_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstitutionTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_name', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('institution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='custom_templates',
                    to='user.institution',
                )),
            ],
            options={
                'unique_together': {('institution', 'template_name')},
            },
        ),
    ]

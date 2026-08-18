# Tests for DeviceTypeAttribute: model, admin CRUD, ordering, institution
# scoping, the suggestions of the product form and the seeding migration.

import importlib

from django.apps import apps as global_apps
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse

from device.forms import DeviceAttributeFormSet, save_device_data
from device.models import DeviceType, DeviceTypeAttribute
from device.tests.test_device_type import make_institution, make_admin, make_user


class DeviceTypeAttributeAdminTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.admin = make_admin(self.institution)
        self.dt = DeviceType.objects.create(institution=self.institution, name="Container")
        self.client = Client()
        self.client.login(email="admin@test.com", password="pass1234")

    def test_flow(self):
        r = self.client.get(reverse('admin:attributes_panel', args=[self.dt.pk]))
        self.assertEqual(r.status_code, 200)

        r = self.client.post(
            reverse('admin:add_device_type_attribute', args=[self.dt.pk]),
            {'name': '  red chairs  '},
        )
        self.assertEqual(r.status_code, 302)
        attr = DeviceTypeAttribute.objects.get()
        self.assertEqual(attr.name, 'red chairs')
        self.assertEqual(attr.order, 1)

        # duplicate, case-insensitive
        self.client.post(
            reverse('admin:add_device_type_attribute', args=[self.dt.pk]),
            {'name': 'RED CHAIRS'},
        )
        self.assertEqual(DeviceTypeAttribute.objects.count(), 1)

        self.client.post(
            reverse('admin:add_device_type_attribute', args=[self.dt.pk]),
            {'name': 'weight'},
        )
        second = DeviceTypeAttribute.objects.get(name='weight')
        self.assertEqual(second.order, 2)

        # reorder
        r = self.client.post(
            reverse('admin:update_device_type_attribute_order', args=[self.dt.pk]),
            {'ordering': f'{second.pk},{attr.pk}'},
        )
        self.assertEqual(r.status_code, 302)
        second.refresh_from_db()
        attr.refresh_from_db()
        self.assertEqual((second.order, attr.order), (1, 2))

        # edit
        self.client.post(
            reverse('admin:edit_device_type_attribute', args=[attr.pk]),
            {'name': 'blue chairs'},
        )
        attr.refresh_from_db()
        self.assertEqual(attr.name, 'blue chairs')

        # delete
        self.client.post(reverse('admin:delete_device_type_attribute', args=[attr.pk]))
        self.assertEqual(DeviceTypeAttribute.objects.count(), 1)

    def test_other_institution_cannot_touch(self):
        other = make_institution("Other")
        make_admin(other, email="other@test.com")
        c = Client()
        c.login(email="other@test.com", password="pass1234")
        attr = DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")

        self.assertEqual(
            c.get(reverse('admin:attributes_panel', args=[self.dt.pk])).status_code, 404)
        self.assertEqual(
            c.post(reverse('admin:edit_device_type_attribute', args=[attr.pk]),
                   {'name': 'hacked'}).status_code, 404)
        self.assertEqual(
            c.post(reverse('admin:delete_device_type_attribute', args=[attr.pk])).status_code,
            404)
        attr.refresh_from_db()
        self.assertEqual(attr.name, 'weight')

    def test_non_admin_cannot_write(self):
        make_user(self.institution, email="plain@test.com")
        c = Client()
        c.login(email="plain@test.com", password="pass1234")
        r = c.post(
            reverse('admin:add_device_type_attribute', args=[self.dt.pk]),
            {'name': 'weight'},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(DeviceTypeAttribute.objects.count(), 0)

    def test_device_type_label_and_icon(self):
        r = self.client.post(
            reverse('admin:edit_device_type', args=[self.dt.pk]),
            {'name': 'Container', 'label': 'Bag', 'icon': 'bi-box'},
        )
        self.assertEqual(r.status_code, 302)
        self.dt.refresh_from_db()
        self.assertEqual(self.dt.label, 'Bag')
        self.assertEqual(self.dt.icon, 'bi-box')
        self.assertEqual(self.dt.display_name, 'Bag')


class NewDeviceSuggestionsTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.user = make_user(self.institution)
        self.dt = DeviceType.objects.create(
            institution=self.institution, name="Container", label="Bag"
        )
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="red chairs")
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")
        self.client = Client()
        self.client.login(email="user@test.com", password="pass1234")

    def test_suggestions_come_from_the_database(self):
        r = self.client.get(reverse('product:add'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.context['device_suggestions'],
            {"Container": ["red chairs", "weight"]},
        )

    def test_suggestions_follow_attribute_order(self):
        DeviceTypeAttribute.objects.filter(name="weight").update(order=0)
        r = self.client.get(reverse('product:add'))
        self.assertEqual(
            r.context['device_suggestions']["Container"], ["weight", "red chairs"]
        )

    def test_select_shows_label_but_keeps_name_as_value(self):
        r = self.client.get(reverse('product:add'))
        choices = r.context['form'].fields['type'].choices
        self.assertIn(("Container", "Bag"), choices)

    def test_other_institution_types_are_not_suggested(self):
        other = make_institution("Other")
        other_type = DeviceType.objects.create(institution=other, name="Pallet")
        DeviceTypeAttribute.objects.create(device_type=other_type, name="high")
        r = self.client.get(reverse('product:add'))
        self.assertNotIn("Pallet", r.context['device_suggestions'])

    def test_type_without_attributes_suggests_nothing(self):
        DeviceType.objects.create(institution=self.institution, name="Pallet")
        r = self.client.get(reverse('product:add'))
        self.assertEqual(r.context['device_suggestions']["Pallet"], [])


class DeviceTypeAttributeModelTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.dt = DeviceType.objects.create(
            institution=self.institution, name="Container")

    def test_name_is_stripped(self):
        attribute = DeviceTypeAttribute.objects.create(
            device_type=self.dt, name="  red chairs  ")
        self.assertEqual(attribute.name, "red chairs")

    def test_order_auto_increments(self):
        first = DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")
        second = DeviceTypeAttribute.objects.create(device_type=self.dt, name="high")
        self.assertEqual((first.order, second.order), (1, 2))

    def test_duplicate_name_ignoring_case_is_rejected(self):
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="Weight")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")

    def test_duplicate_name_after_stripping_is_rejected(self):
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="red chairs")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceTypeAttribute.objects.create(
                    device_type=self.dt, name="red chairs ")

    def test_same_name_is_allowed_in_another_type(self):
        other_type = DeviceType.objects.create(
            institution=self.institution, name="Pallet")
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")
        DeviceTypeAttribute.objects.create(device_type=other_type, name="weight")
        self.assertEqual(DeviceTypeAttribute.objects.filter(name="weight").count(), 2)

    def test_deleting_the_type_drags_its_attributes(self):
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="weight")
        DeviceTypeAttribute.objects.create(device_type=self.dt, name="high")
        self.dt.delete()
        self.assertEqual(DeviceTypeAttribute.objects.count(), 0)


class SnapshotKeysTest(TestCase):
    """The attribute name is the key that ends up in the snapshot, verbatim."""

    def setUp(self):
        self.institution = make_institution()
        self.user = make_user(self.institution)

    def formset(self, pairs):
        data = {
            'form-TOTAL_FORMS': str(len(pairs)),
            'form-INITIAL_FORMS': '0',
        }
        for i, (name, value) in enumerate(pairs):
            data[f'form-{i}-name'] = name
            data[f'form-{i}-value'] = value
        formset = DeviceAttributeFormSet(data=data)
        self.assertTrue(formset.is_valid())
        return formset

    def test_attribute_names_are_the_snapshot_keys(self):
        doc = save_device_data(
            main_data={'type': 'Container'},
            attribute_formset=self.formset([
                ('red chairs', '12'), ('weight', '30kg'),
            ]),
            user=self.user,
            commit=False,
        )
        self.assertEqual(doc['device']['type'], 'Container')
        self.assertEqual(doc['kv'], {'red chairs': '12', 'weight': '30kg'})

    def test_attributes_without_value_are_dropped(self):
        doc = save_device_data(
            main_data={'type': 'Container'},
            attribute_formset=self.formset([('weight', '  '), ('high', '2m')]),
            user=self.user,
            commit=False,
        )
        self.assertEqual(doc['kv'], {'high': '2m'})


class SeedAttributesMigrationTest(TestCase):
    """The 0004 data migration matches pre-existing types case-insensitively."""

    def setUp(self):
        self.migration = importlib.import_module(
            'device.migrations.0004_seed_device_type_attributes')
        self.institution = make_institution()

    def test_matches_a_type_created_in_lowercase(self):
        dt = DeviceType.objects.create(institution=self.institution, name="laptop")
        self.migration.seed_attributes(global_apps, None)
        self.assertEqual(
            [a.name for a in dt.attributes.all()],
            self.migration.SEED_ATTRIBUTES["Laptop"],
        )

    def test_order_is_explicit_and_starts_at_one(self):
        dt = DeviceType.objects.create(institution=self.institution, name="Battery")
        self.migration.seed_attributes(global_apps, None)
        self.assertEqual(
            [a.order for a in dt.attributes.all()],
            list(range(1, len(self.migration.SEED_ATTRIBUTES["Battery"]) + 1)),
        )

    def test_types_outside_the_seed_table_get_nothing(self):
        dt = DeviceType.objects.create(institution=self.institution, name="Container")
        self.migration.seed_attributes(global_apps, None)
        self.assertEqual(dt.attributes.count(), 0)

    def test_reverse_removes_the_seeded_attributes(self):
        dt = DeviceType.objects.create(institution=self.institution, name="Battery")
        self.migration.seed_attributes(global_apps, None)
        self.migration.unseed_attributes(global_apps, None)
        self.assertEqual(dt.attributes.count(), 0)

"""
Tests for DeviceType: model, form, and admin/device views.
"""
import io

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.db import IntegrityError

from user.models import User, Institution
from device.models import DeviceType
from device.forms import DeviceMainForm
from evidence.forms import ImportForm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_institution(name="Test Org"):
    return Institution.objects.create(name=name)


def make_admin(institution, email="admin@test.com", password="pass1234"):
    user = User.objects.create_user(
        email=email,
        institution=institution,
        password=password,
    )
    user.is_admin = True
    user.save()
    return user


def make_user(institution, email="user@test.com", password="pass1234"):
    return User.objects.create_user(
        email=email,
        institution=institution,
        password=password,
    )


# ---------------------------------------------------------------------------
# 1. DeviceType model
# ---------------------------------------------------------------------------

class DeviceTypeModelTest(TestCase):

    def setUp(self):
        self.institution = make_institution()

    def test_create_device_type(self):
        dt = DeviceType.objects.create(institution=self.institution, name="Laptop")
        self.assertEqual(dt.name, "Laptop")
        self.assertEqual(dt.institution, self.institution)

    def test_order_auto_increments(self):
        dt1 = DeviceType.objects.create(institution=self.institution, name="Desktop")
        dt2 = DeviceType.objects.create(institution=self.institution, name="Laptop")
        dt3 = DeviceType.objects.create(institution=self.institution, name="Server")
        self.assertEqual(dt1.order, 1)
        self.assertEqual(dt2.order, 2)
        self.assertEqual(dt3.order, 3)

    def test_order_is_per_institution(self):
        other = make_institution("Other Org")
        dt1 = DeviceType.objects.create(institution=self.institution, name="Desktop")
        dt2 = DeviceType.objects.create(institution=other, name="Desktop")
        # Each institution starts from 1
        self.assertEqual(dt1.order, 1)
        self.assertEqual(dt2.order, 1)

    def test_unique_constraint_same_institution(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        with self.assertRaises(IntegrityError):
            DeviceType.objects.create(institution=self.institution, name="Laptop")

    def test_unique_constraint_ignores_case(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        with self.assertRaises(IntegrityError):
            DeviceType.objects.create(institution=self.institution, name="laptop")

    def test_name_keeps_the_casing_typed_by_the_user(self):
        dt = DeviceType.objects.create(institution=self.institution, name="SolidStateDrive")
        dt.refresh_from_db()
        self.assertEqual(dt.name, "SolidStateDrive")

    def test_same_name_different_institution_allowed(self):
        other = make_institution("Other Org")
        dt1 = DeviceType.objects.create(institution=self.institution, name="Laptop")
        dt2 = DeviceType.objects.create(institution=other, name="Laptop")
        self.assertEqual(dt1.name, dt2.name)

    def test_same_name_different_case_different_institution_allowed(self):
        other = make_institution("Other Org")
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        dt2 = DeviceType.objects.create(institution=other, name="laptop")
        self.assertEqual(dt2.name, "laptop")

    def test_delete_reorders(self):
        dt1 = DeviceType.objects.create(institution=self.institution, name="A")
        dt2 = DeviceType.objects.create(institution=self.institution, name="B")
        dt3 = DeviceType.objects.create(institution=self.institution, name="C")
        # Delete the first one → B should be at order 1, C at order 2
        dt1.delete()
        dt2.refresh_from_db()
        dt3.refresh_from_db()
        self.assertEqual(dt2.order, 1)
        self.assertEqual(dt3.order, 2)

    def test_str(self):
        dt = DeviceType.objects.create(institution=self.institution, name="Camera")
        self.assertIn("Camera", str(dt))
        self.assertIn(self.institution.name, str(dt))

    def test_default_ordering(self):
        DeviceType.objects.create(institution=self.institution, name="C")
        DeviceType.objects.create(institution=self.institution, name="A")
        DeviceType.objects.create(institution=self.institution, name="B")
        names = list(DeviceType.objects.filter(
            institution=self.institution
        ).values_list('name', flat=True))
        # Should come out in insertion order (order 1, 2, 3)
        self.assertEqual(names, ["C", "A", "B"])


# ---------------------------------------------------------------------------
# 2. create_doc accepts custom types (it does not validate against Device.Types)
# ---------------------------------------------------------------------------

class CreateDocCustomTypeTest(TestCase):

    def test_custom_type_does_not_raise(self):
        """create_doc must accept any string as type, not only Device.Types."""
        from utils.device import create_doc
        doc = create_doc({"type": "Rugs", "amount": 1})
        self.assertIsNotNone(doc)
        self.assertEqual(doc["device"]["type"], "Rugs")

    def test_standard_type_still_works(self):
        from utils.device import create_doc
        doc = create_doc({"type": "Laptop", "amount": 1})
        self.assertEqual(doc["device"]["type"], "Laptop")


# ---------------------------------------------------------------------------
# 2b. Excel import validates the type against the DB, ignoring case
# ---------------------------------------------------------------------------

class ImportFormTypeValidationTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.user = make_admin(self.institution)

    def _excel(self, type_value):
        buffer = io.BytesIO()
        pd.DataFrame([{"type": type_value, "model": "X1"}]).to_excel(
            buffer, index=False
        )
        return SimpleUploadedFile(
            "import.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _form(self, type_value):
        return ImportForm(
            data={},
            files={"file_import": self._excel(type_value)},
            user=self.user,
        )

    def test_type_from_db_is_accepted(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        form = self._form("Laptop")
        self.assertTrue(form.is_valid(), form.errors)

    def test_type_is_case_insensitive(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        form = self._form("lAPTOp")
        self.assertTrue(form.is_valid(), form.errors)

    def test_imported_type_is_normalized_to_the_db_spelling(self):
        DeviceType.objects.create(institution=self.institution, name="SolidStateDrive")
        form = self._form("solidstatedrive")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.rows[0]["type"], "SolidStateDrive")

    def test_custom_type_from_db_is_accepted(self):
        DeviceType.objects.create(institution=self.institution, name="Rugs")
        form = self._form("Rugs")
        self.assertTrue(form.is_valid(), form.errors)

    def test_type_not_in_db_is_rejected(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        form = self._form("Toaster")
        self.assertFalse(form.is_valid())

    def test_type_from_another_institution_is_rejected(self):
        other = make_institution("Other Org")
        DeviceType.objects.create(institution=other, name="Laptop")
        DeviceType.objects.create(institution=self.institution, name="Desktop")
        form = self._form("Laptop")
        self.assertFalse(form.is_valid())

    def test_institution_without_types_is_rejected(self):
        form = self._form("Laptop")
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# 3. DeviceMainForm -- dynamic choices
# ---------------------------------------------------------------------------

class DeviceMainFormTest(TestCase):

    def test_no_types_means_empty_choices(self):
        form = DeviceMainForm()
        self.assertEqual(form.fields['type'].choices, [])

    def test_db_types_become_choices_with_empty_option(self):
        custom = [("TypeA", "TypeA"), ("TypeB", "TypeB")]
        form = DeviceMainForm(device_types=custom)
        self.assertEqual(form.fields['type'].choices[1:], custom)
        self.assertEqual(form.fields['type'].choices[0][0], "")

    def test_form_invalid_without_any_type(self):
        data = {'type': 'Laptop', 'amount': 1, 'custom_id': ''}
        form = DeviceMainForm(data=data)
        self.assertFalse(form.is_valid())

    def test_valid_form_with_custom_choices(self):
        custom = [("MyType", "MyType")]
        data = {'type': 'MyType', 'amount': 1, 'custom_id': ''}
        form = DeviceMainForm(data=data, device_types=custom)
        self.assertTrue(form.is_valid())

    def test_invalid_choice_with_custom_choices(self):
        custom = [("MyType", "MyType")]
        data = {'type': 'Laptop', 'amount': 1, 'custom_id': ''}
        form = DeviceMainForm(data=data, device_types=custom)
        self.assertFalse(form.is_valid())
        self.assertIn('type', form.errors)


# ---------------------------------------------------------------------------
# 4. Admin views -- DeviceTypesPanelView, Add, Delete, Edit, Order
# ---------------------------------------------------------------------------

class DeviceTypeAdminViewsTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.admin = make_admin(self.institution)
        self.other_institution = make_institution("Other Org")
        self.other_admin = make_admin(self.other_institution, email="other@test.com")
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass1234")

    # -- Panel --

    def test_panel_requires_login(self):
        self.client.logout()
        url = reverse('admin:devicetypes_panel')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

    def test_panel_requires_admin(self):
        non_admin = make_user(self.institution, email="nonadmin@test.com")
        self.client.login(username="nonadmin@test.com", password="pass1234")
        url = reverse('admin:devicetypes_panel')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_panel_shows_own_institution_types(self):
        DeviceType.objects.create(institution=self.institution, name="Laptop")
        DeviceType.objects.create(institution=self.other_institution, name="Desktop")
        url = reverse('admin:devicetypes_panel')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop")
        self.assertNotContains(response, "Desktop")

    def test_panel_empty_shows_no_types_message(self):
        url = reverse('admin:devicetypes_panel')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No product types found")

    # -- Add --

    def test_add_device_type(self):
        url = reverse('admin:add_device_type')
        response = self.client.post(url, {'name': 'Tablet'})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'))
        self.assertTrue(DeviceType.objects.filter(
            institution=self.institution, name='Tablet'
        ).exists())

    def test_add_device_type_assigns_institution(self):
        url = reverse('admin:add_device_type')
        self.client.post(url, {'name': 'Server'})
        dt = DeviceType.objects.get(institution=self.institution, name='Server')
        self.assertEqual(dt.institution, self.institution)

    # test_add_duplicate_redirects_with_error is in DeviceTypeDuplicateTransactionTest
    # (TransactionTestCase) because IntegrityError in SQLite breaks the outer transaction
    # of TestCase and causes subsequent queries to fail.

    # -- Delete --

    def test_delete_device_type(self):
        dt = DeviceType.objects.create(institution=self.institution, name='HardDrive')
        url = reverse('admin:delete_device_type', kwargs={'pk': dt.pk})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('admin:devicetypes_panel'))
        self.assertFalse(DeviceType.objects.filter(pk=dt.pk).exists())

    def test_delete_other_institution_type_raises_404(self):
        dt = DeviceType.objects.create(institution=self.other_institution, name='Monitor')
        url = reverse('admin:delete_device_type', kwargs={'pk': dt.pk})
        response = self.client.post(url)
        # Must not delete a type from another institution
        self.assertTrue(DeviceType.objects.filter(pk=dt.pk).exists())

    # -- Edit --

    def test_edit_device_type(self):
        dt = DeviceType.objects.create(institution=self.institution, name='OldName')
        url = reverse('admin:edit_device_type', kwargs={'pk': dt.pk})
        response = self.client.post(url, {'name': 'NewName'})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'))
        dt.refresh_from_db()
        self.assertEqual(dt.name, 'NewName')

    # test_edit_to_duplicate_name is in DeviceTypeDuplicateTransactionTest

    def test_edit_other_institution_type_returns_404(self):
        dt = DeviceType.objects.create(institution=self.other_institution, name='SomeType')
        url = reverse('admin:edit_device_type', kwargs={'pk': dt.pk})
        response = self.client.post(url, {'name': 'Renamed'})
        self.assertEqual(response.status_code, 404)

    # -- Update order --

    def test_update_order(self):
        dt1 = DeviceType.objects.create(institution=self.institution, name="First")
        dt2 = DeviceType.objects.create(institution=self.institution, name="Second")
        dt3 = DeviceType.objects.create(institution=self.institution, name="Third")
        url = reverse('admin:update_device_type_order')
        # Reverse the order: dt3 first, dt1 last
        ordering = f"{dt3.pk},{dt2.pk},{dt1.pk}"
        response = self.client.post(url, {'ordering': ordering})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'))
        dt1.refresh_from_db()
        dt2.refresh_from_db()
        dt3.refresh_from_db()
        self.assertEqual(dt3.order, 1)
        self.assertEqual(dt2.order, 2)
        self.assertEqual(dt1.order, 3)

    def test_context_contains_device_types(self):
        DeviceType.objects.create(institution=self.institution, name="Processor")
        url = reverse('admin:devicetypes_panel')
        response = self.client.get(url)
        self.assertIn('device_types', response.context)
        names = list(response.context['device_types'].values_list('name', flat=True))
        self.assertIn("Processor", names)


# ---------------------------------------------------------------------------
# 5. NewDeviceView -- get_form_kwargs reads the types from the DB
# ---------------------------------------------------------------------------

class NewDeviceViewFormKwargsTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.user = make_admin(self.institution)
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass1234")

    def test_no_db_types_leaves_choices_empty(self):
        url = reverse('product:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.fields['type'].choices, [])

    def test_with_db_types_uses_db(self):
        DeviceType.objects.create(institution=self.institution, name="Tablet")
        DeviceType.objects.create(institution=self.institution, name="Phone")
        url = reverse('product:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        choices = form.fields['type'].choices
        self.assertEqual(choices[1:], [("Tablet", "Tablet"), ("Phone", "Phone")])

    def test_db_types_from_other_institution_not_used(self):
        other = make_institution("Other")
        DeviceType.objects.create(institution=other, name="OnlyOther")
        url = reverse('product:add')
        response = self.client.get(url)
        form = response.context['form']
        self.assertEqual(form.fields['type'].choices, [])

    def test_db_types_ordered_by_order_field(self):
        dt1 = DeviceType.objects.create(institution=self.institution, name="Z-Type")
        dt2 = DeviceType.objects.create(institution=self.institution, name="A-Type")
        dt1.order = 2
        dt1.save()
        dt2.order = 1
        dt2.save()
        url = reverse('product:add')
        response = self.client.get(url)
        form = response.context['form']
        choices = form.fields['type'].choices
        self.assertEqual(choices[1], ("A-Type", "A-Type"))
        self.assertEqual(choices[2], ("Z-Type", "Z-Type"))


# ---------------------------------------------------------------------------
# 6. Tests with TransactionTestCase for cases that generate IntegrityError
#    SQLite + TestCase = outer transaction broken after IntegrityError in savepoint.
#    TransactionTestCase cleans the DB between tests (slower but reliable).
# ---------------------------------------------------------------------------

class DeviceTypeDuplicateTransactionTest(TransactionTestCase):
    """Tests that trigger IntegrityError through the HTTP client."""

    def setUp(self):
        self.institution = make_institution()
        self.admin = make_admin(self.institution)
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass1234")

    def test_add_duplicate_redirects_and_does_not_create(self):
        """POST with duplicate name: redirects to panel and does not create a second record."""
        DeviceType.objects.create(institution=self.institution, name='Camera')
        url = reverse('admin:add_device_type')
        response = self.client.post(url, {'name': 'Camera'})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'),
                             fetch_redirect_response=False)
        self.assertEqual(
            DeviceType.objects.filter(institution=self.institution, name='Camera').count(), 1
        )

    def test_add_duplicate_ignoring_case_does_not_create(self):
        DeviceType.objects.create(institution=self.institution, name='Camera')
        url = reverse('admin:add_device_type')
        response = self.client.post(url, {'name': 'camera'})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'),
                             fetch_redirect_response=False)
        self.assertEqual(
            DeviceType.objects.filter(institution=self.institution).count(), 1
        )

    def test_edit_to_duplicate_via_http(self):
        """PUT with an already existing name: redirects and does not modify the record."""
        DeviceType.objects.create(institution=self.institution, name='TypeA')
        dt2 = DeviceType.objects.create(institution=self.institution, name='TypeB')
        url = reverse('admin:edit_device_type', kwargs={'pk': dt2.pk})
        response = self.client.post(url, {'name': 'TypeA'})
        self.assertRedirects(response, reverse('admin:devicetypes_panel'),
                             fetch_redirect_response=False)
        dt2.refresh_from_db()
        self.assertEqual(dt2.name, 'TypeB')  # unchanged

    def test_edit_to_duplicate_ignoring_case_via_http(self):
        DeviceType.objects.create(institution=self.institution, name='TypeA')
        dt2 = DeviceType.objects.create(institution=self.institution, name='TypeB')
        url = reverse('admin:edit_device_type', kwargs={'pk': dt2.pk})
        self.client.post(url, {'name': 'typea'})
        dt2.refresh_from_db()
        self.assertEqual(dt2.name, 'TypeB')

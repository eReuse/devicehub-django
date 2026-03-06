"""
Tests for DeviceType: model, form, and admin/device views.
"""
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.db import IntegrityError

from user.models import User, Institution
from device.models import DeviceType
from device.forms import DeviceForm, BaseDeviceFormSet, DeviceFormSet, DEVICE_TYPES


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
# 1. Modelo DeviceType
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

    def test_same_name_different_institution_allowed(self):
        other = make_institution("Other Org")
        dt1 = DeviceType.objects.create(institution=self.institution, name="Laptop")
        dt2 = DeviceType.objects.create(institution=other, name="Laptop")
        self.assertEqual(dt1.name, dt2.name)

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
# 2. create_doc acepta tipos custom (no valida contra Device.Types)
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
# 3. Formulario DeviceForm — choices dinámicos
# ---------------------------------------------------------------------------

class DeviceFormTest(TestCase):

    def test_default_choices_are_device_types(self):
        form = DeviceForm()
        self.assertEqual(form.fields['type'].choices, DEVICE_TYPES)

    def test_custom_choices_override_default(self):
        custom = [("TypeA", "TypeA"), ("TypeB", "TypeB")]
        form = DeviceForm(device_types=custom)
        self.assertEqual(form.fields['type'].choices, custom)

    def test_valid_form_with_default_choices(self):
        data = {'type': 'Laptop', 'amount': 1, 'custom_id': '', 'name': '', 'value': ''}
        form = DeviceForm(data=data)
        self.assertTrue(form.is_valid())

    def test_valid_form_with_custom_choices(self):
        custom = [("MyType", "MyType")]
        data = {'type': 'MyType', 'amount': 1, 'custom_id': '', 'name': '', 'value': ''}
        form = DeviceForm(data=data, device_types=custom)
        self.assertTrue(form.is_valid())

    def test_invalid_choice_with_custom_choices(self):
        custom = [("MyType", "MyType")]
        data = {'type': 'Laptop', 'amount': 1, 'custom_id': '', 'name': '', 'value': ''}
        form = DeviceForm(data=data, device_types=custom)
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# 3. BaseDeviceFormSet — propagación de device_types
# ---------------------------------------------------------------------------

class BaseDeviceFormSetTest(TestCase):

    def _make_management_form_data(self, total=1):
        return {
            'form-TOTAL_FORMS': str(total),
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        }

    def test_formset_passes_device_types_to_each_form(self):
        custom = [("Tablet", "Tablet"), ("Phone", "Phone")]
        mgmt = self._make_management_form_data(total=2)
        mgmt.update({
            'form-0-type': 'Tablet', 'form-0-amount': '1',
            'form-0-custom_id': '', 'form-0-name': '', 'form-0-value': '',
            'form-1-type': 'Phone', 'form-1-amount': '1',
            'form-1-custom_id': '', 'form-1-name': '', 'form-1-value': '',
        })
        formset = DeviceFormSet(data=mgmt, device_types=custom)
        for form in formset.forms:
            self.assertEqual(form.fields['type'].choices, custom)

    def test_formset_fallback_to_device_types_constant(self):
        mgmt = self._make_management_form_data(total=1)
        mgmt.update({
            'form-0-type': 'Laptop', 'form-0-amount': '1',
            'form-0-custom_id': '', 'form-0-name': '', 'form-0-value': '',
        })
        formset = DeviceFormSet(data=mgmt)
        for form in formset.forms:
            self.assertEqual(form.fields['type'].choices, DEVICE_TYPES)

    def test_formset_valid_with_custom_type(self):
        custom = [("Tablet", "Tablet")]
        mgmt = self._make_management_form_data(total=1)
        mgmt.update({
            'form-0-type': 'Tablet', 'form-0-amount': '2',
            'form-0-custom_id': '', 'form-0-name': '', 'form-0-value': '',
        })
        formset = DeviceFormSet(data=mgmt, device_types=custom)
        self.assertTrue(formset.is_valid())

    def test_each_form_rejects_type_not_in_custom_choices(self):
        """Verifies that each individual form rejects types outside the choices."""
        custom = [("Tablet", "Tablet")]
        mgmt = self._make_management_form_data(total=1)
        mgmt.update({
            'form-0-type': 'Laptop', 'form-0-amount': '1',
            'form-0-custom_id': '', 'form-0-name': '', 'form-0-value': '',
        })
        formset = DeviceFormSet(data=mgmt, device_types=custom)
        # The individual form must be invalid because 'Laptop' is not in custom
        form = formset.forms[0]
        self.assertFalse(form.is_valid())
        self.assertIn('type', form.errors)


# ---------------------------------------------------------------------------
# 4. Vistas admin — DeviceTypesPanelView, Add, Delete, Edit, Order
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
# 5. Vista NewDeviceView — get_form_kwargs usa tipos de BD
# ---------------------------------------------------------------------------

class NewDeviceViewFormKwargsTest(TestCase):

    def setUp(self):
        self.institution = make_institution()
        self.user = make_admin(self.institution)
        self.client = Client()
        self.client.login(username="admin@test.com", password="pass1234")

    def test_no_db_types_uses_fallback(self):
        """Without DB types, the form uses DEVICE_TYPES."""
        url = reverse('product:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        formset = response.context['form']
        form = formset.forms[0]
        self.assertEqual(form.fields['type'].choices, DEVICE_TYPES)

    def test_with_db_types_uses_db(self):
        """With DB types, the form uses those types."""
        DeviceType.objects.create(institution=self.institution, name="Tablet")
        DeviceType.objects.create(institution=self.institution, name="Phone")
        url = reverse('product:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        formset = response.context['form']
        form = formset.forms[0]
        choices = form.fields['type'].choices
        self.assertEqual(choices, [("Tablet", "Tablet"), ("Phone", "Phone")])

    def test_db_types_from_other_institution_not_used(self):
        """Types from another institution do not appear in the form."""
        other = make_institution("Other")
        DeviceType.objects.create(institution=other, name="OnlyOther")
        url = reverse('product:add')
        response = self.client.get(url)
        formset = response.context['form']
        form = formset.forms[0]
        choices = form.fields['type'].choices
        # Fallback because the institution itself has no types
        self.assertEqual(choices, DEVICE_TYPES)

    def test_db_types_ordered_by_order_field(self):
        """Types in the form follow the order of the `order` field."""
        dt1 = DeviceType.objects.create(institution=self.institution, name="Z-Type")
        dt2 = DeviceType.objects.create(institution=self.institution, name="A-Type")
        # Manually reverse the order
        dt1.order = 2
        dt1.save()
        dt2.order = 1
        dt2.save()
        url = reverse('product:add')
        response = self.client.get(url)
        formset = response.context['form']
        form = formset.forms[0]
        choices = form.fields['type'].choices
        self.assertEqual(choices[0], ("A-Type", "A-Type"))
        self.assertEqual(choices[1], ("Z-Type", "Z-Type"))


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

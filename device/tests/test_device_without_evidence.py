from django.test import TestCase

from device.models import Device
from user.models import Institution, User


class DeviceWithoutEvidenceTests(TestCase):
    """A Device is built from an id that may have no evidence behind it, so
    every property has to degrade instead of dereferencing None."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create_user(
            email="u@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.device = Device(id="custom_id:ghost", owner=self.institution)

    def test_there_is_no_evidence(self):
        self.assertIsNone(self.device.get_last_evidence())

    def test_string_properties_are_empty(self):
        for name in ["manufacturer", "model", "serial_number", "type",
                     "cpu", "ram", "version", "updated"]:
            with self.subTest(property=name):
                self.assertEqual(getattr(self.device, name), "")

    def test_collection_properties_are_empty(self):
        self.assertEqual(self.device.components, [])
        self.assertEqual(list(self.device.last_user_evidence), [])

    def test_export_fields_are_filled_with_blanks(self):
        fields = self.device.evidence_export_fields()
        self.assertEqual(fields["ID"], self.device.shortid)
        for key in ["manufacturer", "cpu_model", "ram_total", "drive"]:
            with self.subTest(field=key):
                self.assertEqual(fields[key], "")

    def test_components_export_does_not_fail(self):
        self.assertEqual(self.device.components_export()["manufacturer"], "")

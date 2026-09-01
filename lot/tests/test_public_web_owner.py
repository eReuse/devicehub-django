import uuid as uuidlib

from unittest.mock import patch

from django.test import TestCase, RequestFactory

from evidence.models import SystemProperty
from lot.models import Lot, LotTag, Donor
from lot.views import DonorView
from user.models import Institution, User


class DonorWebOwnerScopeTests(TestCase):
    """The donor page is public, but its url carries the donor uuid, which
    resolves to a lot and therefore to an institution."""

    shared_value = "ereuse24:aaaaaa"
    foreign_value = "ereuse24:bbbbbb"

    def setUp(self):
        self.institution = Institution.objects.create(name="Mine")
        self.user = User.objects.create_user(
            email="mine@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.other_institution = Institution.objects.create(name="Theirs")

        tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="L", owner=self.institution, type=tag)
        self.donor = Donor.objects.create(
            lot=self.lot, email="donor@example.com")

        # the same physical machine processed by both institutions
        for owner in [self.institution, self.other_institution]:
            SystemProperty.objects.create(
                owner=owner, uuid=uuidlib.uuid4(), value=self.shared_value)
        SystemProperty.objects.create(
            owner=self.other_institution,
            uuid=uuidlib.uuid4(),
            value=self.foreign_value,
        )

        self.lot.add(self.shared_value)
        self.lot.add(self.foreign_value)

    def devices(self, MockDevice):
        request = RequestFactory().get("/")
        request.user = self.user
        view = DonorView()
        view.request = request
        view.kwargs = {"pk": self.lot.pk, "id": self.donor.id}
        view.get_object()
        view.get_devices()
        return MockDevice.call_args_list

    @patch("lot.views.Device")
    def test_devices_are_built_with_the_lot_owner(self, MockDevice):
        calls = self.devices(MockDevice)
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call.kwargs["owner"], self.institution)
            self.assertEqual(call.kwargs["lot"], self.lot)

    @patch("lot.views.Device")
    def test_devices_of_another_institution_are_not_listed(self, MockDevice):
        ids = [call.kwargs["id"] for call in self.devices(MockDevice)]
        self.assertEqual(ids, [self.shared_value])

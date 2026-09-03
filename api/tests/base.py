import json
import os
import uuid as uuidlib

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from api.models import Token
from device.models import ProductCache
from evidence.models import SystemProperty
from lot.models import Lot, LotTag
from user.models import Institution, User

BASE_SNAPSHOT = os.path.join(
    settings.BASE_DIR, "example", "snapshots", "snapshot_workbench-script.json")


def load_base_snapshot():
    with open(BASE_SNAPSHOT) as f:
        return json.load(f)


class ApiTestCase(TestCase):
    """Shared fixtures for the v1 API tests.

    Devices are built straight from the database because Evidence only reads
    the Xapian index lazily, so the projection endpoints never need one.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="TestOrg")
        self.user = self.make_user(self.institution, "api@test.com")
        self.token = self.make_token(self.user)
        self.auth = self.bearer(self.token)

    def make_user(self, institution, email, password="pass1234"):
        return User.objects.create_user(
            email=email, institution=institution, password=password)

    def make_token(self, user, is_active=True):
        return Token.objects.create(
            tag="test", token=uuidlib.uuid4(), owner=user, is_active=is_active)

    def bearer(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.token}"}

    def make_device(self, root, institution=None, user=None, **fields):
        """Create the evidence and the projection row a device is made of.

        Saving a SystemProperty fires the signals that self-reference the value
        in RootAlias (what every ID lookup resolves through) and rebuild the
        ProductCache row, which here comes out empty because there is no Xapian
        document behind it; the fields below fill it in.
        """
        institution = institution or self.institution
        prop = SystemProperty.objects.create(
            owner=institution,
            user=user or self.user,
            uuid=uuidlib.uuid4(),
            key=settings.DEVICEHUB_ALGORITHM_DEVICE,
            value=root,
        )
        row = {
            "shortid": root.split(":")[-1][:6].upper(),
            "type": "Laptop",
            "manufacturer": "Dell",
            "model": "Latitude",
            "serial": "SN1",
            "cpu_model": "i7",
            "last_updated": timezone.now(),
            "data": {},
        }
        row.update(fields)
        cache, _ = ProductCache.objects.update_or_create(
            owner=institution, root=root, defaults=row)
        return cache, prop

    def make_lot(self, name="lot-a", institution=None, **fields):
        institution = institution or self.institution
        tag, _ = LotTag.objects.get_or_create(name="Inbox", owner=institution)
        return Lot.objects.create(
            owner=institution, user=self.user, name=name, type=tag, **fields)

    def device_root(self, suffix):
        return f"{settings.DEVICEHUB_ALGORITHM_DEVICE}:{suffix}"

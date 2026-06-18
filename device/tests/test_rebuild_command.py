import uuid as uuidlib
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from user.models import Institution
from evidence.models import SystemProperty
from device.models import ProductCache


class RebuildCommandTests(TestCase):
    def setUp(self):
        self.inst = Institution.objects.create(name="Inst")

    def test_invalid_owner_raises(self):
        with self.assertRaises(CommandError):
            call_command("rebuild_product_cache", "--owner", "999999")

    def test_scopes_to_owner(self):
        other = Institution.objects.create(name="Other")
        with patch.object(ProductCache, "rebuild_all", return_value=3) as m:
            call_command("rebuild_product_cache", "--owner",
                         str(self.inst.id), stdout=StringIO())
        m.assert_called_once_with(owner=self.inst)

    def test_default_scope_is_all(self):
        with patch.object(ProductCache, "rebuild_all", return_value=0) as m:
            call_command("rebuild_product_cache", stdout=StringIO())
        m.assert_called_once_with(owner=None)

    def test_command_never_writes_to_xapian(self):
        # Real rebuild path over a couple of devices; assert the only Xapian
        # writer (evidence.xapian.index) is never invoked.
        SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value="ereuse24:A")
        SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value="ereuse24:B")

        with patch("evidence.xapian.index") as index_mock:
            call_command("rebuild_product_cache", "--owner",
                         str(self.inst.id), stdout=StringIO())
        index_mock.assert_not_called()

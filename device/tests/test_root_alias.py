import uuid
from django.test import TestCase
from device.models import Device
from lot.models import DeviceLot, Lot, LotTag
from user.models import Institution
from evidence.models import SystemProperty, RootAlias


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Test Institution"
        )
        i = self.institution
        lot_tag = LotTag.objects.create(owner=i, name="Incoming")
        self.lot = Lot.objects.create(owner=i, name="lot1", type=lot_tag)
        for x in ["a1", "a2", "a3", "b1", "b3", "c1", "d1", "d2", "z1"]:
            SystemProperty.objects.create(owner=i, uuid=uuid.uuid4(), value=x)
        alias  = [
            # case 1 alias to an other device
            ("a1", "a2"),
            ("a3", "a2"),
            # case2 alias to a custom_id
            ("b1", "b2"),
            ("b3", "b2"),
            # case3 alias with only one to a other device
            ("c1", "c2"),
            # case4 alias with only one to a custom_id
            ("d1", "d2"),
        ]

        for ali, root in alias:
            RootAlias.objects.create(owner=i, alias=ali, root=root)

    def test_queryset_all(self):
        # z1 need to appear
        result = ['a2', 'b1', 'c1', 'd2', 'z1']
        result_orm = [x for x in Device.queryset_orm(self.institution)]
        result_sql = [x[0] for x in Device.queryset_SQL(self.institution)]
        self.assertEqual(result_orm, result_sql)
        self.assertEqual(result_orm, result)

    def test_queryset_unassigned(self):
        result = ['b1', 'c1', 'd2', 'z1']
        DeviceLot.objects.create(lot=self.lot, device_id="a2")
        result_orm = [x for x in Device.queryset_orm_unassigned(self.institution)]
        result_sql = [x[0] for x in Device.queryset_SQL_unassigned(self.institution)]
        self.assertEqual(result_orm, result_sql)
        self.assertEqual(result_orm, result)

import uuid
from django.test import TestCase
from device.models import Device
from user.models import Institution
from utils import sql_query as q_sql
from evidence.models import SystemProperty, RootAlias


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Test Institution"
        )
        i = self.institution
        for x in ["a1", "a2", "a3", "b1", "b3", "c1", "d1", "d2"]:
            SystemProperty.objects.create(owner=i, uuid=uuid.uuid4(), value=x)
        alias  = [
            ("a1", "a2"),
            ("a3", "a2"),
            ("b1", "b2"),
            ("b3", "b2"),
            ("c1", "c2"),
            ("d1", "d2"),
        ]

        for ali, root in alias:
            RootAlias.objects.create(owner=i, alias=ali, root=root)

    def test_queryset_all(self):
        result_orm = [x for x in Device.queryset_orm(self.institution)]
        result_sql = [x[0] for x in q_sql.queryset_SQL(self.institution)]
        self.assertEqual(result_orm, result_sql)

    def test_queryset_unassigned(self):
        result_orm = [x for x in Device.queryset_orm_unassigned(self.institution)]
        result_sql = [x[0] for x in q_sql.queryset_SQL_unassigned(self.institution)]
        self.assertEqual(result_orm, result_sql)

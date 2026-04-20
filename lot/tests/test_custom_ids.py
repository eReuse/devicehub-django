"""
Tests para bugs relacionados con custom_id aliases en lotes y beneficiarios.

Escenario común:
  - Dos devices se añaden a un lote antes de tener alias (se guardan como ereuse24:*)
  - Después se les asigna el mismo custom_id alias
  - El modelo RootAlias guarda: alias=ereuse24:DEVICE, root=custom_id:SAME
"""
import uuid

from django.test import TestCase

from device.models import Device
from evidence.models import RootAlias, SystemProperty
from lot.models import (
    Beneficiary,
    DeviceBeneficiary,
    DeviceLot,
    Lot,
    LotSubscription,
    LotTag,
)
from user.models import Institution, User


class BaseCustomIdTest(TestCase):
    """setUp compartido: institución, usuario, lote."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.user = User.objects.create_user(
            email="test@test.com",
            institution=self.institution,
            password="test",
        )
        self.lot_tag = LotTag.objects.create(
            name="Test Tag", owner=self.institution
        )
        self.lot = Lot.objects.create(
            name="Test Lot",
            owner=self.institution,
            user=self.user,
            type=self.lot_tag,
        )
        self.chid1 = "ereuse24:DEVICE1AAAABBBB"
        self.chid2 = "ereuse24:DEVICE2CCCCDDDD"
        self.custom_id = "custom_id:SAMEALIAS"

    def _make_device(self, chid):
        SystemProperty.objects.create(
            owner=self.institution,
            uuid=uuid.uuid4(),
            key="ereuse24",
            value=chid,
        )

    def _make_alias(self, ereuse24_id, custom_id):
        """alias=ereuse24_id apunta a root=custom_id."""
        RootAlias.objects.create(
            owner=self.institution,
            alias=ereuse24_id,
            root=custom_id,
        )

    def _make_beneficiary(self):
        shop_user = User.objects.create_user(
            email="shop@test.com",
            institution=self.institution,
            password="test",
        )
        subscription = LotSubscription.objects.create(
            lot=self.lot,
            user=shop_user,
            type=LotSubscription.Type.SHOP,
        )
        return Beneficiary.objects.create(
            lot=self.lot,
            shop=subscription,
            email="ben@test.com",
        )


# ---------------------------------------------------------------------------
# Bug 1: dos devices con mismo alias aparecen 2 veces en el lote (debería 1)
# ---------------------------------------------------------------------------

class TestDeduplicationSameAlias(BaseCustomIdTest):
    """
    Bug: dos devices añadidos al lote como ereuse24 IDs y luego mismo alias
    → filter_valid_ids con deduplicate=True debe devolver solo 1 entrada.
    """

    def setUp(self):
        super().setUp()
        self._make_device(self.chid1)
        self._make_device(self.chid2)
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid1)
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid2)
        self._make_alias(self.chid1, self.custom_id)
        self._make_alias(self.chid2, self.custom_id)

    def test_sin_deduplicar_devuelve_dos_entradas(self):
        qs = self.lot.devicelot_set.all()
        result = Device.filter_valid_ids(qs, "device_id", self.institution, deduplicate=False)
        self.assertEqual(result.count(), 2)

    def test_con_deduplicar_devuelve_una_entrada(self):
        qs = self.lot.devicelot_set.all()
        deduped = Device.filter_valid_ids(qs, "device_id", self.institution, deduplicate=True)
        self.assertEqual(deduped.count(), 1)


# ---------------------------------------------------------------------------
# Bug 2: no se puede sacar el device del lote tras asignar mismo alias
# ---------------------------------------------------------------------------

class TestLotRemoveWithSameAlias(BaseCustomIdTest):
    """
    Bug: lot.remove('custom_id:SAME') no encontraba los DeviceLot guardados
    como ereuse24 IDs → el device no se eliminaba del lote.
    """

    def test_remove_devices_guardados_antes_del_alias(self):
        """Devices añadidos al lote antes de tener alias (guardados como ereuse24)."""
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid1)
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid2)
        self._make_alias(self.chid1, self.custom_id)
        self._make_alias(self.chid2, self.custom_id)

        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 2)
        self.lot.remove(self.custom_id)
        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 0)

    def test_remove_device_guardado_despues_del_alias(self):
        """Device añadido al lote después de tener alias (guardado como custom_id)."""
        DeviceLot.objects.create(lot=self.lot, device_id=self.custom_id)
        self._make_alias(self.chid1, self.custom_id)

        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 1)
        self.lot.remove(self.custom_id)
        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 0)

    def test_remove_caso_mixto(self):
        """Un device guardado como ereuse24, otro como custom_id en el mismo lote."""
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid1)
        DeviceLot.objects.create(lot=self.lot, device_id=self.custom_id)
        self._make_alias(self.chid1, self.custom_id)
        self._make_alias(self.chid2, self.custom_id)

        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 2)
        self.lot.remove(self.custom_id)
        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 0)

    def test_remove_sin_alias_no_afecta_otros_devices(self):
        """Sacar un device sin custom_id no borra otros devices del lote."""
        other_chid = "ereuse24:OTHERDEVICE0000"
        DeviceLot.objects.create(lot=self.lot, device_id=self.chid1)
        DeviceLot.objects.create(lot=self.lot, device_id=other_chid)

        self.lot.remove(self.chid1)
        self.assertEqual(DeviceLot.objects.filter(lot=self.lot).count(), 1)
        self.assertTrue(
            DeviceLot.objects.filter(lot=self.lot, device_id=other_chid).exists()
        )


# ---------------------------------------------------------------------------
# Bug 3a: Beneficiary.remove() mismo problema que Lot.remove()
# ---------------------------------------------------------------------------

class TestBeneficiaryRemoveWithSameAlias(BaseCustomIdTest):
    """
    Bug: Beneficiary.remove('custom_id:SAME') no encontraba los
    DeviceBeneficiary guardados como ereuse24 IDs.
    """

    def setUp(self):
        super().setUp()
        self.beneficiary = self._make_beneficiary()

    def test_remove_devices_guardados_antes_del_alias(self):
        """Devices añadidos al beneficiario antes de tener alias."""
        DeviceBeneficiary.objects.create(beneficiary=self.beneficiary, device_id=self.chid1)
        DeviceBeneficiary.objects.create(beneficiary=self.beneficiary, device_id=self.chid2)
        self._make_alias(self.chid1, self.custom_id)
        self._make_alias(self.chid2, self.custom_id)

        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 2
        )
        self.beneficiary.remove(self.custom_id)
        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 0
        )

    def test_remove_device_guardado_despues_del_alias(self):
        """Device añadido al beneficiario después de tener alias (custom_id directo)."""
        DeviceBeneficiary.objects.create(beneficiary=self.beneficiary, device_id=self.custom_id)
        self._make_alias(self.chid1, self.custom_id)

        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 1
        )
        self.beneficiary.remove(self.custom_id)
        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 0
        )


# ---------------------------------------------------------------------------
# Bug 3b: check de beneficiarios en DelToLotView no detectaba el beneficiario
# ---------------------------------------------------------------------------

class TestBeneficiaryCheckBeforeLotRemoval(BaseCustomIdTest):
    """
    Bug: antes de sacar un device del lote se comprueba si tiene beneficiario.
    Si DeviceBeneficiary tenía ereuse24 ID pero se buscaba con custom_id,
    el check devolvía False y permitía eliminar del lote indebidamente.
    """

    def setUp(self):
        super().setUp()
        self.beneficiary = self._make_beneficiary()
        DeviceBeneficiary.objects.create(
            beneficiary=self.beneficiary, device_id=self.chid1
        )
        self._make_alias(self.chid1, self.custom_id)

    def test_check_antiguo_no_detecta_beneficiario(self):
        """Reproduce el bug: buscar con custom_id directo no encuentra el beneficiario."""
        existe = DeviceBeneficiary.objects.filter(
            beneficiary__lot_id=self.lot.id,
            device_id=self.custom_id,
        ).exists()
        self.assertFalse(existe)  # Bug: debería ser True

    def test_check_nuevo_detecta_beneficiario(self):
        """El check nuevo resuelve alias y detecta correctamente el beneficiario."""
        alias_ids = list(
            RootAlias.objects.filter(root=self.custom_id, owner=self.institution)
            .values_list("alias", flat=True)
        )
        ids_to_check = [self.custom_id] + alias_ids
        existe = DeviceBeneficiary.objects.filter(
            beneficiary__lot_id=self.lot.id,
            device_id__in=ids_to_check,
        ).exists()
        self.assertTrue(existe)


# ---------------------------------------------------------------------------
# Bug 3c: DelDeviceBeneficiaryView no borraba DeviceBeneficiary con ereuse24 ID
# ---------------------------------------------------------------------------

class TestDelDeviceBeneficiaryByCustomId(BaseCustomIdTest):
    """
    Bug: la vista usaba device_id=dev_id (custom_id) pero el registro
    en DeviceBeneficiary estaba guardado como ereuse24 → no borraba nada.
    """

    def setUp(self):
        super().setUp()
        self.beneficiary = self._make_beneficiary()
        DeviceBeneficiary.objects.create(
            beneficiary=self.beneficiary, device_id=self.chid1
        )
        self._make_alias(self.chid1, self.custom_id)

    def test_borrado_antiguo_no_elimina_nada(self):
        """Reproduce el bug: filter con custom_id directo no encuentra el registro."""
        DeviceBeneficiary.objects.filter(
            beneficiary_id=self.beneficiary.id,
            device_id=self.custom_id,
        ).delete()
        # Bug: el registro sigue ahí
        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 1
        )

    def test_borrado_nuevo_elimina_por_alias(self):
        """El borrado nuevo resuelve alias y elimina el registro correctamente."""
        alias_ids = list(
            RootAlias.objects.filter(root=self.custom_id, owner=self.institution)
            .values_list("alias", flat=True)
        )
        ids_to_check = [self.custom_id] + alias_ids
        DeviceBeneficiary.objects.filter(
            beneficiary_id=self.beneficiary.id,
            device_id__in=ids_to_check,
        ).delete()
        self.assertEqual(
            DeviceBeneficiary.objects.filter(beneficiary=self.beneficiary).count(), 0
        )


# ---------------------------------------------------------------------------
# Bug 4: deallocate link used ereuse24 ID instead of the canonical custom_id
# ---------------------------------------------------------------------------

class TestDeviceLinkPk(BaseCustomIdTest):
    """
    Bug: ListDevicesBeneficiaryView template built the deallocate link using
    f.device.id (ereuse24:*) instead of f.device.link_pk (custom_id:*), so
    the URL pointed to the raw physical ID rather than the canonical one.

    Fix: use link_pk in the template. The property already existed on Device
    and resolves the alias to the canonical ID when one is present.
    """

    def test_link_pk_without_alias_returns_own_id(self):
        """Without an alias, link_pk is the same as id."""
        device = Device(id=self.chid1, owner=self.institution)
        self.assertEqual(device.link_pk, self.chid1)

    def test_link_pk_with_alias_returns_custom_id(self):
        """With an ereuse24→custom_id alias, link_pk returns the canonical custom_id."""
        self._make_alias(self.chid1, self.custom_id)
        device = Device(id=self.chid1, owner=self.institution)
        self.assertEqual(device.link_pk, self.custom_id)

    def test_link_pk_with_direct_custom_id(self):
        """If the device already has id=custom_id (no alias needed), link_pk returns it."""
        device = Device(id=self.custom_id, owner=self.institution)
        self.assertEqual(device.link_pk, self.custom_id)

    def test_link_pk_two_devices_same_alias_return_same_custom_id(self):
        """Two devices sharing the same alias both return the same link_pk (custom_id)."""
        self._make_alias(self.chid1, self.custom_id)
        self._make_alias(self.chid2, self.custom_id)
        device1 = Device(id=self.chid1, owner=self.institution)
        device2 = Device(id=self.chid2, owner=self.institution)
        self.assertEqual(device1.link_pk, self.custom_id)
        self.assertEqual(device2.link_pk, self.custom_id)

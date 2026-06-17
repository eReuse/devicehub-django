import uuid

from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone

from user.models import Institution
from evidence.models import SystemProperty, RootAlias


class RootAliasSelfReferenceTests(TestCase):
    """Phase 1 of Option 5.

    RootAlias must become the canonical catalog of devices: every
    SystemProperty.value has exactly one RootAlias row where alias=value,
    either as a self-reference (root=value) or pointing to a custom root.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")

    def _new_sp(self, value, owner=None):
        return SystemProperty.objects.create(
            owner=owner or self.institution,
            uuid=uuid.uuid4(),
            value=value,
        )

    # 1.2 — signal

    def test_self_reference_created_on_new_systemproperty(self):
        sp = self._new_sp("ereuse24:A")
        ra = RootAlias.objects.get(owner=self.institution, alias="ereuse24:A")
        self.assertEqual(ra.root, "ereuse24:A")
        self.assertEqual(ra.user_id, sp.user_id)

    def test_self_reference_not_duplicated_for_same_value(self):
        self._new_sp("ereuse24:A")
        self._new_sp("ereuse24:A")  # second evidence for the same device
        self.assertEqual(
            RootAlias.objects.filter(
                owner=self.institution, alias="ereuse24:A"
            ).count(),
            1,
        )

    def test_self_reference_respects_existing_alias(self):
        """If a user alias is created first (hypothetical), a later
        SystemProperty for the same value must not overwrite the root."""
        now = timezone.now()
        RootAlias.objects.create(
            owner=self.institution,
            alias="ereuse24:A",
            root="custom_id:SAME",
            created=now,
            updated=now,
        )
        self._new_sp("ereuse24:A")
        ra = RootAlias.objects.get(owner=self.institution, alias="ereuse24:A")
        self.assertEqual(ra.root, "custom_id:SAME")

    # 1.3 — update_or_create on user alias creation

    def test_create_user_alias_over_self_reference_does_not_collide(self):
        self._new_sp("ereuse24:A")
        # Would have been RootAlias.objects.create(...) and raised
        # IntegrityError on (owner, alias) unique constraint.
        ra, created = RootAlias.objects.update_or_create(
            owner=self.institution,
            alias="ereuse24:A",
            defaults={"root": "custom_id:SAME"},
        )
        self.assertFalse(created)
        self.assertEqual(ra.root, "custom_id:SAME")
        self.assertEqual(
            RootAlias.objects.filter(
                owner=self.institution, alias="ereuse24:A"
            ).count(),
            1,
        )

    def test_unique_constraint_still_enforced(self):
        self._new_sp("ereuse24:A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RootAlias.objects.create(
                    owner=self.institution,
                    alias="ereuse24:A",
                    root="custom_id:OTHER",
                )

    # invariant: every SystemProperty.value has exactly one RootAlias row
    # where alias=value (self-ref or user-set). This is the Phase 1 contract.

    def test_every_systemproperty_value_has_exactly_one_alias_row(self):
        values = ["ereuse24:a1", "ereuse24:a2", "ereuse24:a3", "ereuse24:b1",
                  "ereuse24:b3", "ereuse24:c1", "ereuse24:d1", "ereuse24:d2"]
        for v in values:
            self._new_sp(v)

        for ali, root in [
            ("ereuse24:a1", "ereuse24:a2"),
            ("ereuse24:a3", "ereuse24:a2"),
            ("ereuse24:b1", "ereuse24:b2"),
            ("ereuse24:b3", "ereuse24:b2"),
            ("ereuse24:c1", "ereuse24:c2"),
            ("ereuse24:d1", "ereuse24:d2"),
        ]:
            RootAlias.objects.update_or_create(
                owner=self.institution,
                alias=ali,
                defaults={"root": root},
            )

        for v in values:
            qs = RootAlias.objects.filter(owner=self.institution, alias=v)
            self.assertEqual(qs.count(), 1, msg=f"alias={v}")


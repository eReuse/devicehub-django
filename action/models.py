from django.db import models, connection, transaction
from django.db.models import Count, F, Max
from user.models import User, Institution
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _

from utils.constants import STR_EXTEND_SIZE


# Minimal state every institution has; new devices start in it (order=1).
# State names are user-defined data, so they are never translated.
INITIAL_STATE = "INBOX"

class State(models.Model):
    """Current workflow state of a product, one row per (institution, root).

    ``root`` is a ``RootAlias.root`` value: the product, not an evidence.
    The row is updated in place on every state change; the history lives
    in ``DeviceLog``.

    When a root is merged into another one (``RootAlias.set_alias``) its
    row is kept "dormant": readers only look up live roots, so it is
    invisible, but it gives the alias its previous state back if it is
    split again later.
    """
    # Date of the last state change, set explicitly by writers. It decides
    # which state survives a merge, so it must be copyable (no auto_now).
    date = models.DateTimeField(default=timezone.now)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    root = models.CharField(max_length=STR_EXTEND_SIZE)
    # RESTRICT instead of PROTECT: deleting the Institution cascades to both
    # State and StateDefinition and is allowed, while deleting a single
    # StateDefinition still in use is refused. Deleting a state goes through
    # the admin view, which reassigns its rows (dormant ones included) first.
    state_definition = models.ForeignKey(
        "StateDefinition", on_delete=models.RESTRICT, related_name="states"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "root"], name="state_unique_institution_root"
            ),
        ]

    @property
    def state(self):
        """Name of the current state; keeps ``state.state`` working in
        templates and callers written for the legacy CharField."""
        return self.state_definition.state

    @classmethod
    def live(cls, institution):
        """Rows of live roots: excludes the dormant rows of merged aliases
        (RootAlias rows with alias != root), which no page shows."""
        from evidence.models import RootAlias
        merged = (
            RootAlias.objects.filter(owner=institution)
            .exclude(alias=F("root")).values("alias")
        )
        return cls.objects.filter(institution=institution).exclude(root__in=merged)

    # -- the single "current state" rule ------------------------------------
    # The current state of a product is the State row of its root. Every
    # reader goes through these two helpers; dormant rows are never looked
    # up because callers only pass live roots.

    @classmethod
    def current(cls, institution, root):
        """State row of ``root`` (a RootAlias.root), or None."""
        return (
            cls.objects.select_related("state_definition")
            .filter(institution=institution, root=root).first()
        )

    @classmethod
    def current_by_root(cls, institution, roots):
        """{root: state name} for ``roots`` (RootAlias.root values)."""
        return dict(
            cls.objects.filter(institution=institution, root__in=roots)
            .values_list("root", "state_definition__state")
        )

    @classmethod
    def change(cls, institution, root, state_definition, user=None):
        """Move ``root`` to ``state_definition``; returns the previous
        state name ("" if the root had no row, which should not happen)."""
        with transaction.atomic():
            row = (
                cls.objects.select_for_update().select_related("state_definition")
                .filter(institution=institution, root=root).first()
            )
            previous = row.state_definition.state if row else ""
            if row is None:
                row = cls(institution=institution, root=root)
            row.state_definition = state_definition
            row.user = user
            row.date = timezone.now()
            row.save()
        return previous

    @staticmethod
    def initial_definition(institution):
        """First StateDefinition by order: where new products start.

        Every institution gets INITIAL_STATE from add_institution (or the
        data migration), and the admin can't delete the last state. If an
        institution was created some other way (tests, shell) it is created
        here, so a new device never ends up without a state.
        """
        state_def = (
            StateDefinition.objects.filter(institution=institution)
            .order_by("order", "pk").first()
        )
        if state_def is None:
            state_def = StateDefinition.objects.create(
                institution=institution, state=INITIAL_STATE
            )
        return state_def

    @classmethod
    def create_initial(cls, institution, root, snapshot_uuid, user=None, date=None):
        """Give a new root its initial state and log it.

        ``snapshot_uuid`` is only used for the DeviceLog entry, which is
        still anchored on evidences.
        """
        state_def = cls.initial_definition(institution)
        state = cls.objects.create(
            institution=institution,
            root=root,
            state_definition=state_def,
            user=user,
            date=date or timezone.now(),
        )
        message = gettext("<Created> State '{new}'. Previous State: '{prev}'").format(
            new=state_def.state, prev=gettext("None")
        )
        DeviceLog.objects.create(
            institution=institution,
            user=user,
            event=message,
            snapshot_uuid=snapshot_uuid,
        )
        return state

    @classmethod
    def follow_reroot(cls, institution, alias, old_root, new_root, user=None):
        """Keep State consistent after ``RootAlias.set_alias`` moved
        ``alias`` from ``old_root`` to ``new_root``.

        - Merge (``new_root != alias``): the state the device showed until
          now (``old_root``'s row) is compared with ``new_root``'s row and
          the most recent change wins. A fresh custom_id root gets a copy.
          ``alias``'s own row is left untouched: it becomes dormant.
        - Split (``new_root == alias``): ``alias``'s dormant row is live
          again, so the device gets its previous state back.
        - A custom_id ``old_root`` left without aliases disappears from
          RootAlias, and so does its row here.
        """
        # Lazy import: evidence.models imports this module lazily as well.
        from evidence.models import RootAlias, SystemProperty

        with transaction.atomic():
            roots = {alias, new_root} | ({old_root} if old_root else set())
            rows = {
                s.root: s for s in cls.objects.select_related("state_definition")
                .filter(institution=institution, root__in=roots)
            }
            log_uuid = (
                SystemProperty.objects.filter(owner=institution, value=alias)
                .order_by("-created").values_list("uuid", flat=True).first()
            )

            def log(message):
                if log_uuid:
                    DeviceLog.objects.create(
                        institution=institution, user=user,
                        event=message, snapshot_uuid=log_uuid,
                    )

            def copy(source, root):
                return cls.objects.create(
                    institution=institution, root=root,
                    state_definition=source.state_definition,
                    user=source.user, date=source.date,
                )

            # Legacy safety: every alias should already have its row.
            if alias not in rows:
                source = rows.get(old_root)
                rows[alias] = copy(source, alias) if source else cls.objects.create(
                    institution=institution, root=alias,
                    state_definition=cls.initial_definition(institution),
                )

            # State the device showed before the change.
            current = rows.get(old_root) or rows[alias]

            if new_root == alias:
                restored = rows[alias]
                if restored.state_definition_id != current.state_definition_id:
                    log(gettext(
                        "<Updated> State '{new}' restored after removing the alias. Previous State: '{prev}'"
                    ).format(new=restored.state_definition.state,
                             prev=current.state_definition.state))
            else:
                target = rows.get(new_root)
                if target is None:
                    copy(current, new_root)
                elif current.date > target.date and current.state_definition_id != target.state_definition_id:
                    prev = target.state_definition.state
                    target.state_definition = current.state_definition
                    target.user = current.user
                    target.date = current.date
                    target.save()
                    log(gettext(
                        "<Updated> State '{new}' after merging with '{root}'. Previous State: '{prev}'"
                    ).format(new=current.state_definition.state, root=new_root, prev=prev))

            # alias was its own root: its row is now dormant, never deleted.
            if (
                old_root and old_root not in (alias, new_root)
                and not RootAlias.objects.filter(owner=institution, root=old_root).exists()
            ):
                cls.objects.filter(institution=institution, root=old_root).delete()

    def clean(self):
        if self.state_definition.institution_id != self.institution_id:
            raise ValidationError(
                f"The state '{self.state_definition.state}' is not valid for the institution '{self.institution.name}'."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.institution.name} - {self.state_definition.state} - {self.root}"


class StateDefinition(models.Model):
    institution = models.ForeignKey('user.Institution', on_delete=models.CASCADE)

    order = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True, default='')
    dte_config = models.JSONField(default=dict, blank=True)

    auto_issue_dte = models.BooleanField(
        default=False,
    )

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['institution', 'state'], name='unique_institution_state')
        ]

    def save(self, *args, **kwargs):
        if not self.pk:
            # set the order to be last
            max_order = StateDefinition.objects.filter(institution=self.institution).aggregate(Max('order'))['order__max']
            self.order = (max_order or 0) + 1
        super().save(*args, **kwargs)


    @classmethod
    def product_counts(cls, institution):
        """{state_definition_id: number of products} (dormant rows excluded)."""
        return dict(
            State.live(institution).values("state_definition")
            .annotate(n=Count("pk")).values_list("state_definition", "n")
        )

    def delete_reassigning(self, target=None):
        """Delete this state moving every State row that uses it, dormant
        ones included, to ``target``; returns (target, rows moved).

        ``target`` is mandatory while products show this state. When only
        dormant rows use it, they go to the first other state by order.
        The last state of an institution can't be deleted.
        """
        with transaction.atomic():
            others = (
                StateDefinition.objects.filter(institution=self.institution)
                .exclude(pk=self.pk).order_by("order", "pk")
            )
            if not others.exists():
                raise ValidationError(_("The last state of an organization can't be deleted."))
            if target is None:
                if State.live(self.institution).filter(state_definition=self).exists():
                    raise ValidationError(_("Choose the state its products will move to."))
                target = others.first()
            elif target.institution_id != self.institution_id or target.pk == self.pk:
                raise ValidationError(_("Invalid target state."))
            moved = State.objects.filter(state_definition=self).update(state_definition=target)
            self.delete()
        return target, moved

    def delete(self, *args, **kwargs):
        institution = self.institution
        order = self.order
        super().delete(*args, **kwargs)
        # Adjust the order of other instances
        StateDefinition.objects.filter(institution=institution, order__gt=order).update(order=models.F('order') - 1)

    def __str__(self):
        return f"{self.institution.name} - {self.state}"


class Note(models.Model):
    institution = models.ForeignKey('user.institution', on_delete=models.CASCADE)
    user = models.ForeignKey('user.user', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    snapshot_uuid = models.UUIDField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f" Note: {self.description}, by {self.user.username} @ {self.user.institution} - {self.date}, for {self.snapshot_uuid}"


class DeviceLog(models.Model):
    institution = models.ForeignKey('user.institution', on_delete=models.CASCADE)
    user = models.ForeignKey('user.user', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    event = models.CharField(max_length=255)
    snapshot_uuid = models.UUIDField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.event} by {self.user.username} @ {self.institution.name} - {self.date}, for {self.snapshot_uuid}"

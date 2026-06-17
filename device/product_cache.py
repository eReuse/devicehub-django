from django.db import models

from utils.constants import STR_EXTEND_SIZE
from user.models import Institution


class ProductCache(models.Model):
    """Persistent read model of a device's evidence-derived export fields.

    One row per canonical device, keyed by (owner, root) where root is the
    RootAlias canonical id. Rebuilt from evidence by ProductCache.rebuild()
    and never edited by hand. Relational fields (current_state, beneficiary
    status, user properties) are intentionally NOT stored here: they are cheap
    SQL already and change without a new evidence, so keeping them out limits
    rebuild triggers to two events (a new evidence and a RootAlias change).

    Queried fields (filtered/ordered/searched by the list view) live in their
    own columns so Postgres can index them; display-only export fields live in
    ``data`` to avoid a migration every time the export grows a column.
    """

    # Display-only export fields stored in ``data``. Single source of truth for
    # the JSON payload, shared by the writer (rebuild) and the export reader, so
    # adding/removing a column is a one-line change.
    DATA_FIELDS = (
        "cpu_cores", "ram_total", "ram_type",
        "ram_slots", "slots_used", "drive", "gpu_model",
    )

    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    root = models.CharField(max_length=STR_EXTEND_SIZE)

    shortid = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    type = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    manufacturer = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    model = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    serial = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    cpu_model = models.CharField(max_length=STR_EXTEND_SIZE, default="")
    last_updated = models.DateTimeField(null=True, blank=True)

    # Display-only export payload, keyed by DATA_FIELDS.
    data = models.JSONField(default=dict)

    # When this row was last rebuilt (not the device's evidence date).
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "root"], name="productcache_unique"),
        ]
        indexes = [
            models.Index(
                fields=["owner", "-last_updated"],
                name="productcache_owner_lastupd_idx"),
        ]

    @classmethod
    def rebuild(cls, owner, root):
        """(Re)build the projection row for one canonical device.

        The single entry point that knows how to populate a row; every trigger
        (the SystemProperty signal, set_alias, the management command) funnels
        through here. Returns the row, or None if the root has no evidence, in
        which case any stale row is removed.
        """
        from device.models import Device

        device = Device(id=root, owner=owner)
        device.get_uuids()
        if not device.uuids:
            cls.objects.filter(owner=owner, root=root).delete()
            return None

        f = device.merged_export_fields()
        data = {k: f.get(k, "") for k in cls.DATA_FIELDS}
        # Raw per-disk power-on-hours history, kept under its own nested key so
        # the flat DATA_FIELDS reads are unaffected.
        data["storage"] = device.storage_readings()
        obj, _ = cls.objects.update_or_create(
            owner=owner,
            root=root,
            defaults={
                "shortid": f.get("ID", "") or "",
                "type": f.get("type", "") or "",
                "manufacturer": f.get("manufacturer", "") or "",
                "model": f.get("model", "") or "",
                "serial": f.get("serial", "") or "",
                "cpu_model": f.get("cpu_model", "") or "",
                "last_updated": f.get("last_updated") or None,
                "data": data,
            },
        )
        return obj

    @classmethod
    def drop(cls, owner, root):
        """Remove the projection row for a root that is no longer canonical."""
        cls.objects.filter(owner=owner, root=root).delete()

    @classmethod
    def rebuild_all(cls, owner=None):
        """Rebuild projections for every canonical device.

        Iterates DISTINCT RootAlias.root per owner (the canonical device set)
        and rebuilds each. Pass ``owner`` to scope to one institution. Returns
        the number of roots processed.
        """
        from evidence.models import RootAlias

        institutions = [owner] if owner is not None else list(
            Institution.objects.all())
        total = 0
        for inst in institutions:
            roots = (
                RootAlias.objects.filter(owner=inst)
                .values_list("root", flat=True)
                .distinct()
            )
            for root in roots:
                cls.rebuild(inst, root)
                total += 1
        return total

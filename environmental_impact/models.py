from django.db import models
from django.core.exceptions import ValidationError
from user.models import Institution
from utils.constants import STR_EXTEND_SIZE


class EnvironmentalImpact:
    def __init__(self):
        self.kg_CO2e: dict = {}
        self.relevant_input_data: dict = {}
        self.constants: dict = {}
        self.docs: str = ""


class DiskChangeEvent(models.Model):
    """
    Records when a disk change is detected in a device.

    A disk change is identified when comparing disk metadata (model,
    manufacturer, serialNumber) between consecutive evidences.
    """

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    device_chid = models.CharField(max_length=STR_EXTEND_SIZE, db_index=True)
    # Evidence UUID where the disk change was detected
    evidence_uuid = models.UUIDField(db_index=True)
    # Evidence index in the chronological sequence (0-based)
    evidence_index = models.IntegerField(
        help_text="Index in chronological sequence (0 = first evidence)"
    )
    # Disk metadata for tracking
    old_disk_serial = models.CharField(
        max_length=STR_EXTEND_SIZE, blank=True, null=True
    )
    new_disk_serial = models.CharField(
        max_length=STR_EXTEND_SIZE, blank=True, null=True
    )
    old_disk_model = models.CharField(max_length=STR_EXTEND_SIZE, blank=True, null=True)
    new_disk_model = models.CharField(max_length=STR_EXTEND_SIZE, blank=True, null=True)
    # Power-on hours at the time of detection
    poh_before_change = models.IntegerField(
        null=True, blank=True, help_text="PoH from evidence before disk change"
    )
    poh_after_change = models.IntegerField(
        null=True, blank=True, help_text="PoH from evidence with new disk"
    )
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)

    class Meta:
        ordering = ["device_chid", "evidence_index"]
        unique_together = ["device_chid", "evidence_uuid"]
        indexes = [
            models.Index(fields=["device_chid", "evidence_index"]),
        ]
        db_table = "disk_change_events"  # Explicit table naming

    def __str__(self):
        return (
            f"Disk change for {self.device_chid} " f"at evidence {self.evidence_index}"
        )


class DeviceLifecycleMetrics(models.Model):
    """
    Metrics:
    - total_usage_time): Total accumulated powered-on hours
    - reuse_time: Hours of reuse (second life)
    """

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    device_chid = models.CharField(
        max_length=STR_EXTEND_SIZE, unique=True, db_index=True
    )
    total_usage_time = models.IntegerField(
        default=0, help_text="Total accumulated powered-on hours"
    )
    reuse_time = models.IntegerField(
        default=0, help_text="Hours of reuse (second life)"
    )
    # Number of evidences processed
    evidence_count = models.IntegerField(default=0)
    # Number of disk changes detected
    disk_change_count = models.IntegerField(default=0)
    # UUID of first evidence (for tracking)
    first_evidence_uuid = models.UUIDField(null=True, blank=True)
    # UUID of last evidence (for tracking)
    last_evidence_uuid = models.UUIDField(null=True, blank=True)
    first_poh = models.IntegerField(
        null=True, blank=True, help_text="Power-on hours from the first evidence"
    )
    last_poh = models.IntegerField(
        null=True, blank=True, help_text="Power-on hours from the last evidence"
    )
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Device Lifecycle Metric"
        verbose_name_plural = "Device Lifecycle Metrics"
        ordering = ["-updated"]

    def __str__(self):
        return (
            f"Metrics for {self.device_chid}: "
            f"T_T={self.total_usage_time}h, T_R={self.reuse_time}h"
        )

    def clean(self):
        """Validate that reuse_time <= total_usage_time."""
        if self.reuse_time > self.total_usage_time:
            raise ValidationError("Reuse time  cannot exceed total usage time")

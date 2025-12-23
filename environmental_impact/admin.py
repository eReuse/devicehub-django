from django.contrib import admin
from environmental_impact.models import (
    DeviceLifecycleMetrics,
    DiskChangeEvent
)


@admin.register(DeviceLifecycleMetrics)
class DeviceLifecycleMetricsAdmin(admin.ModelAdmin):
    list_display = [
        'device_chid',
        'total_usage_time',
        'reuse_time',
        'evidence_count',
        'disk_change_count',
        'updated'
    ]
    search_fields = ['device_chid']
    list_filter = ['owner', 'updated', 'disk_change_count']
    readonly_fields = ['created', 'updated']


@admin.register(DiskChangeEvent)
class DiskChangeEventAdmin(admin.ModelAdmin):
    list_display = [
        'device_chid',
        'evidence_index',
        'old_disk_model',
        'new_disk_model',
        'poh_before_change',
        'poh_after_change',
        'created'
    ]
    search_fields = ['device_chid', 'evidence_uuid']
    list_filter = ['owner', 'created']
    readonly_fields = ['created', 'updated']

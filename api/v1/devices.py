import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from device.models import Device
from api.auth import GlobalAuth
from api.v1.lots import _check_valid_ids
from api.v1.schemas import MessageOut, SuccessResponse, PropertyIn, DeviceWithLogsOut, BulkPropertyIn, OperationResult
from evidence.models import UserProperty, RootAlias, SystemProperty
from action.models import DeviceLog

logger = logging.getLogger('django')


router = Router(tags=["Devices"])


def _log_registry(_uuid, msg, user):
    DeviceLog.objects.create(
        snapshot_uuid=_uuid,
        event=msg,
        user=user,
        institution=user.institution
    )

def _get_device(pk: str, user):
    """
    Checks whether `pk` is a valid device id.
    """
    institution = user.institution
    clean_pk = pk.split(":")[-1] if ":" in pk else pk
    base_qs = RootAlias.objects.filter(owner=institution)

    strategies = [
        base_qs.filter(alias=pk),
        base_qs.filter(alias__endswith=f":{clean_pk}")
    ]

    if len(clean_pk) >= 6:
        short_id = clean_pk[:6]
        strategies.append(base_qs.filter(alias__contains=f":{short_id}"))

    strategies.append(base_qs.filter(alias__icontains=clean_pk))

    root = None

    for qs in strategies:
        count = qs.count()
        if count == 1:
            root = qs.first()
            break
        elif count > 1:
            raise HttpError(
                400,
                "Multiple devices found matching this identifier. Please be more specific (e.g., provide the full ID)."
            )

    if not root:
        raise HttpError(404, "Device does not exist")

    canonical_id = root.root
    device = Device(id=canonical_id)

    if hasattr(device, 'last_evidence') and not device.last_evidence:
        raise HttpError(404, "Device does not exist or lacks evidence")

    return device


@router.get(
    "/devices/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Retrieve a specific device property"),
    description=_("""
    Fetch detailed information about a particular user property associated with a device.
    """),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def get_property(request, device_id: str, key: str):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        # Fetch property directly using device_id per new DB schema
        prop = UserProperty.objects.get(
            owner=user.institution,
            device_id=device.id,
            key=key
        )

        return {
            "status": "success",
            "property": {
                "key": prop.key,
                "value": prop.value,
                "device_id": device.id,
                "created_at": prop.created
            }
        }
    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except UserProperty.DoesNotExist:
        raise HttpError(404, "Property not found")


@router.delete(
    "/devices/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Remove a device's user property"),
    description=_("""
    Permanently deletes a custom user property from a device.
    """),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def delete_property(request, device_id: str, key: str):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        prop = UserProperty.objects.get(
            owner=user.institution,
            device_id=device.id,
            key=key
        )

        old_key = prop.key
        old_value = prop.value
        prop_time = prop.created
        prop.delete()

        log_message = f"<Deleted> User Property: {old_key}:{old_value}"
        if device.last_evidence:
            _log_registry(device.last_evidence.uuid, log_message, user)

        return {
            "status": "success",
            "property": {
                "keY": old_key,
                "value": old_value,
                "device_id": device.id,
                "created_at": prop_time
            },
            "action": "deleted"
        }

    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except UserProperty.DoesNotExist:
        raise HttpError(404, "Property not found")
    except HttpError:
        raise
    except Exception as e:
        logger.exception(f"Error deleting property {key} from device {device_id}")
        raise HttpError(500, "Internal server error")


@router.post(
    "/devices/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 201: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Create or update device's user property"),
    description=_("""
    Sets or modifies a custom user property on a device.
    """),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def set_property(request, device_id: str, key: str, data: PropertyIn):
    user = request.auth
    try:
        device = _get_device(device_id, user)

        try:
            prop = UserProperty.objects.get(
                owner=user.institution,
                device_id=device.id,
                key=key
            )
            old_value = prop.value
            prop.value = data.value
            prop.save()

            action = "updated"
            status_code = 200
            log_message = f"<Updated> UserProperty: {key}: {old_value} to {key}: {data.value}"

        except UserProperty.DoesNotExist:
            prop = UserProperty.objects.create(
                device_id=device.id,
                type=UserProperty.Type.USER,
                key=key,
                value=data.value,
                owner=user.institution,
                user=user,
            )
            action = "created"
            status_code = 201
            log_message = f"<Created> UserProperty: {key}: {data.value}"

        if device.last_evidence:
            _log_registry(device.last_evidence.uuid, log_message, user)

        return status_code, {
            "status": "success",
            "action": action,
            "property": {
                "key": prop.key,
                "value": prop.value,
                "device_id": device.id,
                "created_at": prop.created
            }
        }

    except IntegrityError:
        raise HttpError(400, "Property configuration or integrity error.")
    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except HttpError:
        raise
    except Exception as e:
        logger.exception(f"Error updating property {key} for device {device_id}")
        raise HttpError(500, "Internal server error")

@router.get(
    "/{device_id}/logs/",
    response={
        200: DeviceWithLogsOut,
        403: MessageOut,
        404: MessageOut
    },
    summary=_("Get device details and audit logs"),
    description=_("""
    Retrieves the complete hardware/software specifications of a device
    alongside its historical timeline of events (property changes, state changes, etc.).
    """),
    tags=["Devices"],
    auth=GlobalAuth()
)
def get_device_logs(request, device_id: str):
    user = request.auth
    institution = user.institution

    try:
        device = _get_device(device_id, user)

        device_data = device.components_export()

        aliases = RootAlias.physical_aliases(institution, device.id)

        uuids = SystemProperty.objects.filter(
            owner=institution,
            value__in=aliases
        ).values_list('uuid', flat=True)

        logs_qs = DeviceLog.objects.filter(
            institution=institution,
            snapshot_uuid__in=uuids
        ).order_by('-date')

        logs_data = [
            {
                "event": log.event,
                "date": log.date,
                "user": log.user.username if log.user else "System",
                "snapshot_uuid": str(log.snapshot_uuid)
            }
            for log in logs_qs
        ]

        return {
            "device": device_data,
            "logs": logs_data
        }

    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except HttpError:
        raise
    except Exception as e:
        logger.exception(f"Error fetching logs and details for device {device_id}")
        raise HttpError(500, "Internal server error")


@router.post(
    "/bulk-properties/",
    response={
        200: OperationResult,
        207: OperationResult,
        400: MessageOut,
        403: MessageOut,
        422: MessageOut
    },
    summary=_("Bulk assign a user property"),
    description=_("""
    Assigns or updates a specific UserProperty across multiple devices simultaneously.

    Accepts partial hashes, short IDs, or exact aliases. Ambiguous identifiers are rejected.

    Returns:
    - 200: Property successfully applied to all devices
    - 207: Partial success (some identifiers were invalid/ambiguous)
    - 422: No valid devices provided
    """),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def bulk_assign_properties(request, data: BulkPropertyIn):
    user = request.auth
    institution = user.institution

    try:
        valid_ids, invalid_ids = _check_valid_ids(data.device_ids, institution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided or all matches were ambiguous")

        existing_props = UserProperty.objects.filter(
            owner=institution,
            device_id__in=valid_ids,
            key=data.key,
            type=UserProperty.Type.USER
        )
        existing_map = {p.device_id: p for p in existing_props}

        devices = [Device(id=id) for id in valid_ids]
        device_map = {d.id: d for d in devices}

        props_to_create = []
        props_to_update = []
        logs_to_create = []

        for canonical_id in valid_ids:
            device = device_map.get(canonical_id)
            if not device:
                continue

            if canonical_id in existing_map:
                prop = existing_map[canonical_id]
                old_val = prop.value
                prop.value = data.value
                props_to_update.append(prop)
                log_msg = f"<Updated> UserProperty: {data.key}: {old_val} to {data.key}: {data.value}"
            else:
                props_to_create.append(
                    UserProperty(
                        device_id=canonical_id,
                        type=UserProperty.Type.USER,
                        key=data.key,
                        value=data.value,
                        owner=institution,
                        user=user,
                    )
                )
                log_msg = f"<Created> UserProperty: {data.key}: {data.value}"

            if hasattr(device, 'last_evidence') and device.last_evidence:
                logs_to_create.append(
                    DeviceLog(
                        institution=institution,
                        user=user,
                        event=log_msg,
                        snapshot_uuid=device.last_evidence.uuid
                    )
                )

        if props_to_create:
            UserProperty.objects.bulk_create(props_to_create, ignore_conflicts=True)
        if props_to_update:
            UserProperty.objects.bulk_update(props_to_update, fields=['value'])
        if logs_to_create:
            DeviceLog.objects.bulk_create(logs_to_create)

        response = OperationResult(
            success=True,
            processed_ids=list(valid_ids),
            invalid_ids=list(invalid_ids),
            message="Some IDs were invalid or ambiguous" if invalid_ids else f"Property '{data.key}' successfully applied."
        )
        return 200 if not invalid_ids else 207, response

    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except HttpError:
        raise
    except Exception as e:
        logger.exception("Error executing bulk property assignment")
        raise HttpError(500, "Internal server error")

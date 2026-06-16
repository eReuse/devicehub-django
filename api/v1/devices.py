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
    "/{device_id}/",
    response={
        200: DeviceResponse,
        403: MessageOut,
        404: MessageOut
    },
    summary=_("Get complete device information"),
    description=_("""
    Retrieves comprehensive technical specifications and metadata for a device.

    Includes:
    - Hardware specifications (CPU, RAM, storage etc.)
    - Custom user properties
    - Current device state
    - Last update timestamp

    Responses:
    - 200: Full device details
    - 403: Access denied
    - 404: Device not found
    """),
    tags=["Devices"],
    auth=GlobalAuth()
)
def get_device_details(request, device_id: str):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        device_data = device.components_export()
        return DeviceResponse(**device_data)

    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except ObjectDoesNotExist:
        raise HttpError(404, "Property not found")

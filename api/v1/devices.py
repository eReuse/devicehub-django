import json
import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist

from lot.models import Lot
from device.models import Device
from api.auth import GlobalAuth
from api.v1.schemas import DeviceResponse, MessageOut, PropertyOut, SuccessResponse, PropertyIn
from evidence.models import UserProperty
from action.models import StateDefinition, State, DeviceLog, Note

logger = logging.getLogger('django')


router = Router(tags=["Devices"])


def _log_registry(_uuid, msg, user):
    DeviceLog.objects.create(
        snapshot_uuid=_uuid,
        event=msg,
        user=user,
        institution=user.institution
    )

def _get_device(pk, user):
    """ Checks whether pl is a valid device id"""
    device = Device(id=pk)
    if not device.last_evidence:
        raise HttpError(404, "Device does not exist")
    if device.owner != user.institution:
        raise PermissionDenied("Permission denied")
    return device


@router.get(
    "/devices/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 403: MessageOut, 404: MessageOut},
    summary="Get device property",
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def get_property(request, device_id: str, key: str):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        prop = device.get_user_properties().get(key=key)

        return {
            "status": "success",
            "property": {
                "key": prop.key,
                "value": prop.value,
                "device_id": device.pk,
                "created_at": prop.created
            }
        }
    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except ObjectDoesNotExist:
        raise HttpError(404, "Property not found")

@router.delete(
    "/devices/{device_id}/properties/{key}/",
    response={
        200: SuccessResponse,
        403: MessageOut,
        404: MessageOut
    },
    summary="Delete device property",
    description="Deletes a specific property from a device if it exists",
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def delete_property(request, device_id: str, key: str):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        prop = device.get_user_properties().get(key=key)
        prop.delete()

        log_message = f"Deleted property: {key}"
        _log_registry(device.properties[0].uuid, log_message, user)

        return {
            "status": "success",
            "property": {
                "key": prop.key,
                "value": prop.value,
                "device_id": device.id,
                "created_at": prop.created
            },
            "action": "deleted"
        }

    except PermissionDenied:
        raise HttpError(403, "Access denied")
    except ObjectDoesNotExist:
        raise HttpError(404, "Property not found")
    except Exception as e:
        logger.exception(f"Error deleting property {key} from device {device_id}")
        raise HttpError(500, "Internal server error")

    
@router.post(
    "/devices/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 201: SuccessResponse, 400: MessageOut, 403: MessageOut},
    summary="Create or update device property",
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def set_property(request, device_id: str, key: str, data: PropertyIn):
    user = request.auth
    try:
        device = _get_device(device_id, user)
        try:
            prop = device.get_user_properties().get(key=key)
            prop.value = data.value
            prop.save()
            action = "updated"
            status_code = 200
        except UserProperty.DoesNotExist:
            uuid = device.properties[0].uuid
            prop = UserProperty.objects.create(
                uuid=uuid,
                type=UserProperty.Type.USER,
                key=key,
                value=data.value,
                owner=user.institution,
                user=user,
            )
            action = "created"
            status_code = 201

        log_message = f"<{action.capitalize()}> property: {key}: {data.value}"
        _log_registry(prop.uuid, log_message, user)

        return status_code, {
            "status": "success",
            "action": action,
            "property": {
                "key": prop.key,
                "value": prop.value,
                "device_id": device.pk,
                "created_at": prop.created
            }
        }

    except PermissionDenied:
        raise HttpError(403, "Access denied")
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
    summary="Get device details",
    description="Retrieve comprehensive information about a specific device",
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

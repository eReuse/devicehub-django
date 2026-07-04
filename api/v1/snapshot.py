import json
import logging

from ninja import Body
from ninja import Router
from ninja.errors import HttpError
from django.urls import reverse
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from utils.save_snapshots import move_json, save_in_disk
from evidence.models import SystemProperty
from evidence.parse import Build
from device.models import Device
from .schemas import SnapshotResponse, MessageOut
from api.auth import GlobalAuth

logger = logging.getLogger('django')

router = Router(tags=["Snapshot"])

@router.post(
    "/",
    response={
        200: SnapshotResponse,
        400: MessageOut,
        409: MessageOut,
        422: MessageOut,
        500: MessageOut
    },
    summary=_("Process device snapshot"),
    description=_("""
    Upload and process a workbench snapshot JSON file to register or update device information.

    Returns:
    - 200: Success - Snapshot processed successfully
    - 400: Bad Request - Invalid JSON format
    - 409: Conflict - Snapshot with this UUID already exists
    - 422: Unprocessable Entity - Invalid snapshot structure or missing required fields
    - 500: Internal Server Error - Unexpected processing failure
    """),
    tags=["Snapshots"],
    url_name="upload_snapshot",
    auth=GlobalAuth()
)
def NewSnapshot(request, data: dict = Body(..., description="Paste the raw workbench JSON snapshot here")):
    user = request.auth

    # validate payload
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON received: %s", str(e))
        raise HttpError(400, str(e))

    #check for duplicate before saving onto disk
    ev_uuid = data.get("uuid")
    if data.get("credentialSubject"):
       ev_uuid = data["credentialSubject"].get("uuid")

    if not ev_uuid:
        logger.error("Received snapshot without UUID")
        raise HttpError(422, "Snapshot must contain a UUID")

    if SystemProperty.objects.filter(uuid=ev_uuid).exists():
        logger.warning("Duplicate snapshot received with UUID: %s", ev_uuid)
        raise HttpError(409, f"UUID {ev_uuid} is already registered")

    try:
        path_name = save_in_disk(data, user.institution.name)
    except Exception as e:
        logger.error("Failed to save snapshot to disk: %s", str(e))
        raise HttpError(500, "Could not save snapshot file")

    try:
        Build(data, None, check=True)
    except Exception as e:
        logger.warning("Snapshot validation failed: %s", str(e))
        raise HttpError(422, str(e))

    try:
        Build(data, user)
    except Exception as err:
        if settings.DEBUG:
            logger.exception("%s", err)
        snapshot_id = ev_uuid
        txt = "It is not possible to parse snapshot: %s."
        logger.error(txt, snapshot_id)
        raise HttpError(500, str(err))

    prop = SystemProperty.objects.filter(
        uuid=ev_uuid,
        # TODO this is hardcoded, it should select The user preferred algorithm
        key="ereuse24",
        owner=user.institution
    ).first()

    if not prop:
        logger.error("System property not created for UUID: %s", ev_uuid)
        raise HttpError(500, "Could not create device property")

    url_args = reverse("device:details", args=(prop.value,))
    url = request.build_absolute_uri(url_args)

    url_public_args = reverse("device:device_web", args=(prop.value,))
    url_public = request.build_absolute_uri(url_public_args)

    move_json(path_name, user.institution.name)
    response = {
        "status": "success",
        "dhid": Device.get_shortid_for(prop.value, prop.owner),
        "url": url,
        # TODO replace with public_url when available
        "public_url": url_public
    }
    return response

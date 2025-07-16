import json
import logging

from ninja import Router, File
from ninja.files import UploadedFile
from django.urls import reverse_lazy
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from utils.save_snapshots import move_json, save_in_disk
from evidence.models import SystemProperty
from evidence.parse import Build
from .schemas import SnapshotResponse, MessageOut
from api.auth import GlobalAuth

logger = logging.getLogger('django')

router = Router(tags=["Lots"])

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
    auth=GlobalAuth()
)
def NewSnapshot(request, snapshot: UploadedFile = File(...)):
    user = request.auth

    # Validation snapshot
    try:
        data = json.loads(snapshot.read())
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON received: %s", str(e))
        return 400, {
            "error": "Invalid JSON format",
            "details": str(e)
        }

    # Process snapshot
    try:
        path_name = save_in_disk(data, user.institution.name)
    except Exception as e:
        logger.error("Failed to save snapshot to disk: %s", str(e))
        return 500, {
            "error": "Internal server error",
            "details": "Could not save snapshot file"
        }

    try:
        Build(data, None, check=True)
    except Exception as e:
        logger.warning("Snapshot validation failed: %s", str(e))
        return 422, {
            "error": "Invalid snapshot structure",
            "details": str(e)
        }

    ev_uuid = data.get("uuid")
    if data.get("credentialSubject"):
       ev_uuid = data["credentialSubject"].get("uuid")

    if not ev_uuid:
        logger.error("Received snapshot without UUID")
        return 422, {
            "error": "Missing required field",
            "details": "Snapshot must contain a UUID"
        }

    exist_property = SystemProperty.objects.filter(
        uuid=ev_uuid
    ).first()

    if exist_property:
        logger.warning("Duplicate snapshot received with UUID: %s", ev_uuid)
        return 409, {
            "error": "Snapshot already exists",
            "details": f"UUID {ev_uuid} is already registered"
        }

    try:
        Build(data, user)
    except Exception as err:
        if settings.DEBUG:
            logger.exception("%s", err)
        snapshot_id = ev_uuid
        txt = "It is not possible to parse snapshot: %s."
        logger.error(txt, snapshot_id)
        return 500, {
            "error": "Snapshot processing failed",
            "details": str(err)
        }

    prop = SystemProperty.objects.filter(
        uuid=ev_uuid,
        # TODO this is hardcoded, it should select the user preferred algorithm
        key="ereuse24",
        owner=user.institution
    ).first()

    if not prop:
        logger.error("System property not created for UUID: %s", ev_uuid)
        return 500, {
            "error": "Internal server error",
            "details": "Could not create device property"
        }

    url_args = reverse_lazy("device:details", args=(prop.value,))
    url = request.build_absolute_uri(url_args)

    move_json(path_name, user.institution.name)
    response = {
        "status": "success",
        "dhid": prop.value[:6].upper(),
        "url": url,
        # TODO replace with public_url when available
        "public_url": url
    }
    return response

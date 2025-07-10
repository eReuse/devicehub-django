import json
import logging

from ninja import Router
from ninja.errors import HttpError
from django.urls import reverse_lazy
from django.conf import settings

from utils.save_snapshots import move_json, save_in_disk
from evidence.models import SystemProperty
from evidence.parse import Build

logger = logging.getLogger('django')

router = Router(tags=["Lots"])

@router.post("/snapshot/")
def NewSnapshot(request):
    owner = request.auth
    # Validation snapshot
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        txt = "error: the snapshot is not a json"
        logger.error("%s", txt)
        raise HttpError(500, 'Invalid JSON')

    # Process snapshot
    path_name = save_in_disk(data, owner.institution.name)

    # try:
    #     Build(data, None, check=True)
    # except Exception:
    #     return HttpError(400, 'Invalid Snapshot')

    ev_uuid = data.get("uuid")
    if data.get("credentialSubject"):
       ev_uuid = data["credentialSubject"].get("uuid")

    if not ev_uuid:
        txt = "error: the snapshot does not have an uuid"
        logger.error("%s", txt)
        raise HttpError(500, txt)

    exist_property = SystemProperty.objects.filter(
        uuid=ev_uuid
    ).first()

    if exist_property:
        txt = "error: the snapshot {} exist".format(ev_uuid)
        logger.warning("%s", txt)
        return HttpError(500, txt)


    try:
        Build(data, owner)
    except Exception as err:
        if settings.DEBUG:
            logger.exception("%s", err)
        snapshot_id = ev_uuid
        txt = "It is not possible to parse snapshot: %s."
        logger.error(txt, snapshot_id)
        text = "fail: It is not possible to parse snapshot. {}".format(err)
        return HttpError(500, text)

    prop = SystemProperty.objects.filter(
        uuid=ev_uuid,
        # TODO this is hardcoded, it should select the user preferred algorithm
        key="ereuse24",
        owner=owner.institution
    ).first()


    if not prop:
         logger.error("Error: No property  for uuid: %s", ev_uuid)
         return HttpError(500, 'fail')

    url_args = reverse_lazy("device:details", args=(prop.value,))
    url = request.build_absolute_uri(url_args)

    response = {
        "status": "success",
        "dhid": prop.value[:6].upper(),
        "url": url,
        # TODO replace with public_url when available
        "public_url": url
    }
    move_json(path_name, owner.institution.name)

    return response

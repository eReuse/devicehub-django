import logging

from django.utils.translation import gettext_lazy as _
from ninja import Router
from ninja.errors import HttpError

from action.models import DeviceLog
from evidence.models import RootAlias, SystemProperty

from api.auth import GlobalAuth
from api.v1.schemas import EvidenceAliasOut, MessageOut


logger = logging.getLogger('django')
router = Router(tags=["Evidence"])


@router.put(
    "/{alias}/aliases/{root}/",
    response={200: EvidenceAliasOut, 403: MessageOut, 404: MessageOut, 409: MessageOut, 422: MessageOut},
    summary=_("Point an evidence to another canonical identifier"),
    description=_("""
    Rewrite which canonical identifier an evidence belongs to.

    The evidence is named by its own identifier, the one every snapshot of the
    same device shares. The wanted root is read the same way the web form reads
    it: if it matches an existing evidence identifier the two are merged under
    it, otherwise it is taken as an operator-assigned identifier and stored as
    `custom_id:<value>`.

    Lot and beneficiary memberships follow the device to its new identity.

    Returns:
    - 200: The evidence now resolves to the given root
    - 404: No evidence of the institution answers to that identifier
    - 409: The change would chain two aliases together, either because the
      target is itself aliased or because other evidences already point here
    - 422: The wanted root is the evidence itself
    """),
    tags=["Evidence"],
    auth=GlobalAuth(),
)
def set_evidence_alias(request, alias: str, root: str):
    user = request.auth
    institution = user.institution

    alias = alias.strip()
    current = RootAlias.objects.filter(owner=institution, alias=alias).first()
    if not current:
        raise HttpError(404, _("Evidence identifier does not exist"))

    wanted = root.strip().lower()
    if not wanted:
        raise HttpError(422, _("The wanted root is empty"))
    if wanted == alias:
        raise HttpError(422, _("The wanted root is the evidence itself"))

    if SystemProperty.objects.filter(owner=institution, value=wanted).exists():
        new_root = wanted
    else:
        new_root = "custom_id:{}".format(wanted)

    old_root = current.root
    if old_root == new_root:
        return {"status": "success", "alias": alias, "root": new_root}

    try:
        RootAlias.set_alias(
            owner=institution, alias=alias, new_root=new_root, user=user)
    except ValueError as e:
        raise HttpError(409, str(e))

    _log(institution, user, alias, _(
        "<Updated> Evidence alias. Old Value: '{}'. New Value: '{}'").format(
            old_root, new_root))

    return {"status": "success", "alias": alias, "root": new_root}


@router.delete(
    "/{alias}/aliases/",
    response={200: EvidenceAliasOut, 403: MessageOut, 404: MessageOut},
    summary=_("Give an evidence back its own identifier"),
    description=_("""
    Undo the alias of an evidence, so it answers to itself again.

    The row is not deleted: every evidence identifier keeps a canonical entry,
    which is what lets lot and beneficiary memberships travel back to the
    device's own identity.

    Returns:
    - 200: The evidence is canonical again
    - 404: No evidence of the institution answers to that identifier
    """),
    tags=["Evidence"],
    auth=GlobalAuth(),
)
def reset_evidence_alias(request, alias: str):
    user = request.auth
    institution = user.institution

    alias = alias.strip()
    current = RootAlias.objects.filter(owner=institution, alias=alias).first()
    if not current:
        raise HttpError(404, _("Evidence identifier does not exist"))

    old_root = current.root
    if old_root == alias:
        return {"status": "success", "alias": alias, "root": alias}

    _log(institution, user, alias,
         _("<Deleted> Evidence alias: {}").format(old_root))

    RootAlias.set_alias(
        owner=institution, alias=alias, new_root=alias, user=user)

    return {"status": "success", "alias": alias, "root": alias}


def _log(institution, user, alias, event):
    uuid = SystemProperty.objects.filter(
        owner=institution, value=alias
    ).order_by("-created").values_list("uuid", flat=True).first()

    if uuid:
        DeviceLog.objects.create(
            snapshot_uuid=uuid,
            event=event,
            user=user,
            institution=institution,
        )

import math
import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import File, Form, Router, Query
from ninja.errors import HttpError
from ninja.files import UploadedFile
from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _

from evidence.models import UserProperty, RootAlias, SystemProperty
from evidence.forms import PhotoForm
from device.forms import DeviceAttributeFormSet, DeviceMainForm
from device.models import Device, DeviceType, ProductCache
from action.models import DeviceLog

from api.auth import GlobalAuth
from api.v1.schemas import MessageOut, SuccessResponse, PropertyIn, DeviceWithLogsOut, BulkPropertyIn, OperationResult, DeviceListResponse, ProductIn, ProductCreatedResponse, ProductTypeOut, PhotoUploadedResponse

from api.v1.utils import get_device_instance, resolve_device_root, check_valid_ids, get_all_search_results, build_device_response_list, build_bulk_device_export_dict


logger = logging.getLogger('django')
router = Router(tags=["Devices"])

def _log_registry(_uuid, msg, user):
    DeviceLog.objects.create(
        snapshot_uuid=_uuid,
        event=msg,
        user=user,
        institution=user.institution
    )

@router.get(
    "/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Retrieve a specific device property"),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def get_property(request, device_id: str, key: str):
    device = get_device_instance(device_id, request.auth)
    prop = get_object_or_404(UserProperty, owner=request.auth.institution, device_id=device.id, key=key)

    return {
        "status": "success",
        "property": {
            "key": prop.key,
            "value": prop.value,
            "device_id": device.id,
            "created_at": prop.created
        }
    }

@router.delete(
    "/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Remove a device's user property"),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def delete_property(request, device_id: str, key: str):
    user = request.auth
    device = get_device_instance(device_id, user)

    prop = get_object_or_404(UserProperty, owner=user.institution, device_id=device.id, key=key)

    old_key, old_value, prop_time = prop.key, prop.value, prop.created
    prop.delete()

    if device.last_evidence:
        _log_registry(device.last_evidence.uuid, f"<Deleted> User Property: {old_key}:{old_value}", user)

    return {
        "status": "success",
        "property": {
            "key": old_key,
            "value": old_value,
            "device_id": device.id,
            "created_at": prop_time
        },
        "action": "deleted"
    }

@router.post(
    "/{device_id}/properties/{key}/",
    response={200: SuccessResponse, 201: SuccessResponse, 400: MessageOut, 403: MessageOut, 404: MessageOut},
    summary=_("Create or update device's user property"),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def set_property(request, device_id: str, key: str, data: PropertyIn):
    user = request.auth
    device = get_device_instance(device_id, user)

    try:
        with transaction.atomic():
            prop, created = UserProperty.objects.get_or_create(
                owner=user.institution,
                device_id=device.id,
                key=key,
                defaults={
                    'type': UserProperty.Type.USER,
                    'value': data.value,
                    'user': user
                }
            )

            if created:
                action, status_code = "created", 201
                log_msg = f"<Created> UserProperty: {key}: {data.value}"
            else:
                old_value = prop.value
                if old_value != data.value:
                    prop.value = data.value
                    prop.save(update_fields=['value'])

                action, status_code = "updated", 200
                log_msg = f"<Updated> UserProperty: {key}: {old_value} to {key}: {data.value}"

            if device.last_evidence:
                _log_registry(device.last_evidence.uuid, log_msg, user)

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
        raise HttpError(400, "Integrity error.")

@router.get(
    "/{device_id}/logs/",
    response={200: DeviceWithLogsOut, 403: MessageOut, 404: MessageOut},
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
        device = get_device_instance(device_id, user)
        devices_export = build_device_response_list([device.id], institution)
        dev_data = devices_export[0] if devices_export else {}

        aliases = RootAlias.physical_aliases(institution, device.id)
        uuids = SystemProperty.objects.filter(owner=institution, value__in=aliases).values_list('uuid', flat=True)

        logs_qs = DeviceLog.objects.filter(institution=institution, snapshot_uuid__in=uuids).select_related('user').order_by('-date')
        logs_data = [
            {"event": log.event, "date": log.date, "user": log.user.username if log.user else "System", "snapshot_uuid": str(log.snapshot_uuid)}
            for log in logs_qs
        ]
        return {"device": dev_data, "logs": logs_data}
    except HttpError: raise
    except Exception as e:
        logger.exception(f"Error fetching logs for {device_id}")
        raise HttpError(500, "Internal server error")


@router.post(
    "/bulk-properties/",
    response={200: OperationResult, 207: OperationResult, 400: MessageOut, 403: MessageOut, 422: MessageOut},
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

    valid_ids, invalid_ids = check_valid_ids(data.device_ids, institution)
    if not valid_ids: raise HttpError(422, "No valid device IDs provided")

    try:

        existing_map = {p.device_id: p for p in UserProperty.objects.filter(owner=institution, device_id__in=valid_ids, key=data.key, type=UserProperty.Type.USER)}
        devices = [Device(id=id, owner=institution) for id in valid_ids]

        props_to_create, props_to_update, logs_to_create = [], [], []

        for device in devices:
            if device.id in existing_map:
                prop = existing_map[device.id]
                log_msg = f"<Updated> UserProperty: {data.key}: {prop.value} to {data.key}: {data.value}"
                prop.value = data.value
                props_to_update.append(prop)
            else:
                props_to_create.append(UserProperty(device_id=device.id, type=UserProperty.Type.USER, key=data.key, value=data.value, owner=institution, user=user))
                log_msg = f"<Created> UserProperty: {data.key}: {data.value}"

            if hasattr(device, 'last_evidence') and device.last_evidence:
                logs_to_create.append(DeviceLog(institution=institution, user=user, event=log_msg, snapshot_uuid=device.last_evidence.uuid))

        with transaction.atomic():
            if props_to_create: UserProperty.objects.bulk_create(props_to_create, ignore_conflicts=True)
            if props_to_update: UserProperty.objects.bulk_update(props_to_update, fields=['value'])
            if logs_to_create: DeviceLog.objects.bulk_create(logs_to_create)

        return (200 if not invalid_ids else 207), OperationResult(
            success=True, processed_ids=list(valid_ids), invalid_ids=list(invalid_ids),
            message="Some IDs were invalid or ambiguous" if invalid_ids else f"Property '{data.key}' successfully applied."
        )
    except Exception as e:
        logger.exception("Error executing bulk property assignment")
        raise HttpError(500, "Internal server error")


@router.get(
    "/",
    response={200: DeviceListResponse, 403: MessageOut},
    summary=_("Retrieve all devices (Paginated)"),
    description=_("""
    Get all devices across the institution with pagination.
    """),
    tags=["Devices"],
    auth=GlobalAuth(),
)
def list_all_devices(
    request,
    q: str = Query(None, description="Optional search query (ShortID or Text)"),
    prop_key: str = Query(None, description="Filter by UserProperty key"),
    prop_value: str = Query(None, description="Filter by UserProperty value"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=50, description="Items per page")
):
    user = request.auth
    institution = user.institution

    # apply filters
    valid_ids_set = None
    if prop_key or prop_value:
        prop_qs = UserProperty.objects.filter(owner=institution, type=UserProperty.Type.USER)
        if prop_key: prop_qs = prop_qs.filter(key=prop_key)
        if prop_value: prop_qs = prop_qs.filter(value=prop_value)
        valid_ids_set = set(prop_qs.values_list("device_id", flat=True))

    # search
    if q and q.strip():
        search_ids = get_all_search_results(q.strip(), institution)
        chids_ordered = [x for x in search_ids if (valid_ids_set is None or x in valid_ids_set)]
    else:
        cache_qs = ProductCache.objects.filter(owner=institution).order_by('-last_updated')
        if valid_ids_set is not None:
            cache_qs = cache_qs.filter(root__in=valid_ids_set)
        chids_ordered = list(cache_qs.values_list('root', flat=True))

    total_items = len(chids_ordered)
    total_pages = math.ceil(total_items / size) if total_items > 0 else 1

    if total_items == 0 or page > total_pages:
        return DeviceListResponse(
            pagination={"total_items": total_items, "total_pages": total_pages, "current_page": page, "page_size": size},
            devices=[]
        )

    # slice then fetch device data
    offset = (page - 1) * size
    chids_page = chids_ordered[offset : offset + size]

    devices_export = build_device_response_list(chids_page, institution)

    return DeviceListResponse(
        pagination={"total_items": total_items, "total_pages": total_pages, "current_page": page, "page_size": size},
        devices=devices_export
    )

@router.get(
    "/types/",
    response={200: list[ProductTypeOut], 403: MessageOut},
    summary=_("List the product types of the institution"),
    description=_("""
    Retrieves the product types an operator can choose from, each one with the
    attribute names suggested for it.

    These are the values accepted by the product registration endpoint: the type
    goes in `type` and the suggested attributes are a starting point for
    `attributes`, which is not restricted to them.
    """),
    tags=["Devices"],
    auth=GlobalAuth()
)
def get_product_types(request):
    device_types = DeviceType.objects.filter(
        institution=request.auth.institution
    ).order_by('order').prefetch_related('attributes')

    return [
        {
            "name": device_type.name,
            "display_name": device_type.display_name,
            "icon": device_type.icon,
            "attributes": [a.name for a in device_type.attributes.all()],
        }
        for device_type in device_types
    ]


API_FIELD_NAMES = {"photo_file": "photo"}


def _attribute_formset(attributes):
    """Feeds the web formset from a plain mapping of attribute names to values."""
    data = {"form-TOTAL_FORMS": str(len(attributes)), "form-INITIAL_FORMS": "0"}
    for position, (name, value) in enumerate(attributes.items()):
        data[f"form-{position}-name"] = name
        data[f"form-{position}-value"] = value
    return DeviceAttributeFormSet(data)


def _form_errors(form, formset=None):
    messages = [
        "{}: {}".format(API_FIELD_NAMES.get(field, field) or "__all__", " ".join(errors))
        for field, errors in form.errors.items()
    ]
    if formset:
        messages += [
            "attributes: {}".format(" ".join(errors))
            for form_errors in formset.errors for errors in form_errors.values()
        ]
    return "; ".join(messages)


@router.post(
    "/",
    response={201: ProductCreatedResponse, 403: MessageOut, 422: MessageOut},
    summary=_("Register a product manually"),
    description=_("""
    Register a product without a workbench snapshot, the same way the web form does.

    The payload travels as form data, so a photo of the product can be attached
    to the same request. Attributes go in a single field holding a JSON object.

    The type must be one of the product types configured by the institution.
    Any other characteristic is sent as a free-form attribute name/value pair.

    A custom ID becomes the canonical identifier of the product and must not be
    in use; giving one registers a single product regardless of the amount asked.
    Attaching a photo registers a single product as well, and the photo is
    stored as its own evidence linked to the product.

    Returns:
    - 201: Products registered
    - 422: Unknown product type, custom ID already in use, rejected photo, or invalid payload
    """),
    tags=["Devices"],
    auth=GlobalAuth(),
)
def create_product(request, data: Form[ProductIn], photo: UploadedFile = File(None)):
    user = request.auth
    institution = user.institution

    device_types = DeviceType.objects.filter(institution=institution).order_by('order')

    form = DeviceMainForm(
        data={
            "type": data.type,
            "amount": data.amount,
            "custom_id": data.custom_id or "",
        },
        files={"photo_file": photo} if photo else None,
        user=user,
        device_types=[(dt.name, dt.display_name) for dt in device_types],
    )
    formset = _attribute_formset(data.attributes)

    if not form.is_valid() or not formset.is_valid():
        raise HttpError(422, _form_errors(form, formset))

    docs = form.save(attribute_formset=formset)

    products = []
    for doc in docs:
        web_id = doc["WEB_ID"]
        root = RootAlias.objects.filter(
            owner=institution, alias=web_id
        ).values_list('root', flat=True).first() or web_id

        products.append({
            "ID": root,
            "dhid": Device.get_shortid_for(web_id, institution),
            "url": request.build_absolute_uri(
                reverse("product:details", args=(web_id,))),
            "public_url": request.build_absolute_uri(
                reverse("product:device_web", args=(web_id,))),
        })

    return 201, {"status": "success", "products": products}


@router.post(
    "/{device_id}/photo/",
    response={201: PhotoUploadedResponse, 403: MessageOut, 404: MessageOut, 422: MessageOut},
    summary=_("Attach a photo to an existing product"),
    description=_("""
    Upload a single photo and link it to a product that is already registered.

    The product is identified in the path. Any identifier it answers to works:
    the canonical one, a custom ID, or the id of one of its evidences; the photo
    is always linked to the canonical id behind it.

    The photo is stored as an evidence of its own, so the same image cannot be
    uploaded twice.

    Returns:
    - 201: Photo stored and linked
    - 404: No product answers to that identifier
    - 422: Rejected photo
    """),
    tags=["Devices"],
    auth=GlobalAuth(),
)
def upload_product_photo(request, device_id: str, photo: UploadedFile = File(...)):
    user = request.auth
    institution = user.institution

    root = resolve_device_root(device_id, institution)
    if not root:
        raise HttpError(404, _("Product does not exist"))

    form = PhotoForm(files={"photo_file": photo}, user=user)
    if not form.is_valid():
        raise HttpError(422, _form_errors(form))

    doc = form.save()
    photo_prop = SystemProperty.objects.get(uuid=doc["uuid"], key="photo25")
    RootAlias.set_alias(
        owner=institution, alias=photo_prop.value, new_root=root, user=user)

    return 201, {
        "status": "success",
        "ID": root,
        "uuid": doc["uuid"],
        "url": request.build_absolute_uri(
            reverse("evidence:photo_file", args=(doc["uuid"],))),
    }


@router.get(
    "/properties/keys/",
    response={200: list[str], 403: MessageOut},
    summary=_("Get all unique property keys"),
    description=_("Retrieves an alphabetical list of all distinct UserProperty keys currently in use by the institution."),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def get_property_keys(request):
    institution = request.auth.institution

    keys = UserProperty.objects.filter(
        owner=institution,
        type=UserProperty.Type.USER
    ).values_list('key', flat=True).distinct().order_by('key')

    return list(keys)


@router.get(
    "/properties/{key}/values/",
    response={200: list[str], 403: MessageOut},
    summary=_("Get all unique values for a property key"),
    description=_("Retrieves an alphabetical list of all distinct values assigned to a specific UserProperty key."),
    tags=["Device Properties"],
    auth=GlobalAuth()
)
def get_property_values(request, key: str):
    institution = request.auth.institution

    values = UserProperty.objects.filter(
        owner=institution,
        key=key,
        type=UserProperty.Type.USER
    ).values_list('value', flat=True).distinct().order_by('value')

    return list(values)

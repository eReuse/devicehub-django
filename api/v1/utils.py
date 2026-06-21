import logging
from ninja.errors import HttpError
from lot.models import Lot
from evidence.models import RootAlias
from device.models import Device

logger = logging.getLogger('django')

def find_lot(identifier: str, institution):
    """ Find lot by either name:(str) or pk:(int) """
    try:
        if identifier.isdigit():
            return Lot.objects.get(id=int(identifier), owner=institution)
        return Lot.objects.get(name=identifier, owner=institution)
    except Lot.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Invalid lot identifier: {identifier} - {e}")
        return None

def resolve_device_root(pk: str, owner, strict=False):
    """
    Resolves a device hash/ID.
    If strict=True, raises a 400 error on multiple matches.
    If strict=False, safely returns None for bulk processing.
    """
    clean_pk = pk.split(":")[-1] if ":" in pk else pk
    base_qs = RootAlias.objects.filter(owner=owner)

    strategies = [
        base_qs.filter(alias=pk),
        base_qs.filter(alias__endswith=f":{clean_pk}")
    ]

    if len(clean_pk) >= 6:
        short_id = clean_pk[:6]
        strategies.append(base_qs.filter(alias__contains=f":{short_id}"))

    strategies.append(base_qs.filter(alias__icontains=clean_pk))

    for qs in strategies:
        count = qs.count()
        if count == 1:
            return qs.first().root
        elif count > 1:
            if strict:
                raise HttpError(
                    400,
                    "Multiple devices found matching this identifier. Please be more specific."
                )
            return None

    return None

def get_device_instance(pk: str, user):
    """Strictly fetches a Device instance, ensuring it has evidence."""
    canonical_id = resolve_device_root(pk, user.institution, strict=True)
    if not canonical_id:
        raise HttpError(404, "Device does not exist")

    device = Device(id=canonical_id, owner=user.institution)
    if hasattr(device, 'last_evidence') and not device.last_evidence:
        raise HttpError(404, "Device does not exist or lacks evidence")

    return device

def check_valid_ids(device_ids, owner):
    """Processes a bulk list of IDs into valid canonical roots and invalid entries."""
    valid_ids = set()
    invalid_ids = set()
    pending_ids = set(device_ids)

    exact_matches = RootAlias.objects.filter(owner=owner, alias__in=pending_ids)

    for match in exact_matches:
        valid_ids.add(match.root)
        pending_ids.remove(match.alias)

    for pk in pending_ids:
        canonical_id = resolve_device_root(pk, owner, strict=False)
        if canonical_id:
            valid_ids.add(canonical_id)
        else:
            invalid_ids.add(pk)

    return valid_ids, invalid_ids

def build_device_export_dict(cache, device):
    """Standardizes the dictionary construction from the Cache and Device models."""
    dev_data = {
        "ID": cache.root,
        "shortId": cache.shortid,
        "manufacturer": cache.manufacturer,
        "type": cache.type,
        "model": cache.model,
        "serial": cache.serial,
        "cpu_model": cache.cpu_model,
        "last_updated": cache.last_updated,
    }

    dev_data.update(cache.data)

    current_state = device.get_current_state()
    dev_data["current_state"] = current_state.state if current_state else ""
    dev_data["beneficiary_status"] = device.status_beneficiary or ""
    dev_data["user_properties"] = {x.key: x.value for x in device.get_user_properties()}

    return dev_data

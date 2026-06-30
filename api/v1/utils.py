import re
import json
import logging
from django.db.models import Q
from ninja.errors import HttpError

from lot.models import Lot, DeviceBeneficiary
from evidence.models import RootAlias, SystemProperty, UserProperty
from device.models import Device, ProductCache
from action.models import State
from evidence.xapian import search

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
    Resolves a device hash/ID or Custom ID.
    Returns the canonical root ID for the first match found.
    """
    clean_pk = pk.split(":")[-1] if ":" in pk else pk
    base_qs = RootAlias.objects.filter(owner=owner)

    strategies = [
        base_qs.filter(Q(root__iexact=pk) | Q(alias__iexact=pk)),

        base_qs.filter(Q(root__iendswith=f":{clean_pk}") | Q(alias__iendswith=f":{clean_pk}")),

        base_qs.filter(Q(root__icontains=f":{clean_pk}") | Q(alias__icontains=f":{clean_pk}")),

        base_qs.filter(alias__iexact=clean_pk)
    ]

    for qs in strategies:
        root = qs.values_list('root', flat=True).first()
        if root:
            return root

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
    valid_ids, invalid_ids, pending_ids = set(), set(), set(device_ids)
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


# search functions by xapian and shortid (copied from view)
def _build_shortid_qry(terms, field):
    exact_qry, partial_qry = Q(), Q()
    for term in terms:
        exact_qry |= Q(**{f"{field}__iregex": r'^[^:]+:' + re.escape(term)})
        max_offset = 6 - len(term)
        if max_offset > 0:
            rqry = r'^[^:]+:[^:]{1,' + str(max_offset) + r'}' + re.escape(term)
            partial_qry |= Q(**{f"{field}__iregex": rqry})
    return exact_qry, partial_qry


def search_shortid_ids(query_str, institution):
    """Search SystemProperty by shortid and RootAlias by root shortid."""
    terms = [t for t in query_str.split() if t]

    if not terms or len(terms) > 1:
        return []

    exact_qry, partial_qry = _build_shortid_qry(terms, "value")

    exact_values = list(
        SystemProperty.objects.filter(owner=institution)
        .filter(exact_qry).values_list("value", flat=True).distinct()
    )

    seen_exact = set(exact_values)
    partial_values = []
    if partial_qry:
        partial_values = [
            v for v in SystemProperty.objects.filter(owner=institution)
            .filter(partial_qry).values_list("value", flat=True).distinct()
            if v not in seen_exact
        ]

    values = exact_values + partial_values

    alias_map = dict(
        RootAlias.objects.filter(owner=institution, alias__in=values)
        .values_list("alias", "root")
    )

    seen = set()
    ids = []
    for value in values:
        canonical = alias_map.get(value, value)
        if canonical not in seen:
            seen.add(canonical)
            ids.append(canonical)

    exact_root_qry, partial_root_qry = _build_shortid_qry(terms, "root")
    exact_roots = list(
        RootAlias.objects.filter(owner=institution)
        .filter(exact_root_qry).values_list("root", flat=True).distinct()
    )
    for root in exact_roots:
        if root not in seen:
            seen.add(root)
            ids.append(root)

    if partial_root_qry:
        partial_roots = [
            v for v in RootAlias.objects.filter(owner=institution)
            .filter(partial_root_qry).values_list("root", flat=True).distinct()
            if v not in seen
        ]
        for root in partial_roots:
            seen.add(root)
            ids.append(root)

    return ids


def get_xapian_results(query_str, institution, offset, limit):
    """Returns (xapian_count, list_of_canonical_roots_in_page)"""
    if not search:
        return 0, []

    matches = search(institution, query_str, 0, 9999)
    if not matches:
        return 0, []

    total_count = matches.size()

    if limit <= 0:
        return total_count, []

    page_matches = search(institution, query_str, offset, limit)
    if not page_matches or page_matches.size() == 0:
        return total_count, []

    uuids = []
    for x in page_matches:
        try:
            snap = json.loads(x.document.get_data())
            uuid = snap.get("credentialSubject", {}).get("uuid") or snap.get("uuid")
            if uuid:
                uuids.append(uuid)
        except Exception as err:
            logger.error(f"Xapian parse error: {err}")

    if not uuids:
        return total_count, []

    props = SystemProperty.objects.filter(
        owner=institution, uuid__in=uuids,
    ).values_list("uuid", "value")

    uuid_to_value = {str(u): v for u, v in props}

    ordered_aliases = [uuid_to_value[uuid] for uuid in uuids if uuid in uuid_to_value]

    alias_map = dict(
        RootAlias.objects.filter(owner=institution, alias__in=ordered_aliases)
        .values_list("alias", "root")
    )

    ordered_roots = [alias_map.get(a, a) for a in ordered_aliases]

    return total_count, ordered_roots

def get_all_search_results(query_str, institution):
    """Returns a fully ordered, combined list of all device root IDs matching a search string."""
    sp_ids = search_shortid_ids(query_str, institution)
    _, xapian_page = get_xapian_results(query_str, institution, 0, 9999)

    seen = set(sp_ids)
    combined = list(sp_ids)
    for x in xapian_page:
        if x not in seen:
            seen.add(x)
            combined.append(x)
    return combined


# bulk orm queries - - -

def fetch_bulk_device_data(chids_page, institution, lot=None):
    """Executes the 4 heavy SQL queries required for export payloads in bulk."""

    #user properties
    user_props_qs = UserProperty.objects.filter(owner=institution, device_id__in=chids_page)
    props_map = {}
    for prop in user_props_qs:
        props_map.setdefault(prop.device_id, {})[prop.key] = prop.value

    # get beneficiaries
    default_ben_status = str(DeviceBeneficiary.Status.AVAILABLE.label)
    dev_bens = DeviceBeneficiary.objects.filter(device_id__in=chids_page, beneficiary__lot=lot) if lot else DeviceBeneficiary.objects.filter(device_id__in=chids_page)
    ben_map = {db.device_id: str(DeviceBeneficiary.Status(db.status).label) for db in dev_bens}

    # states
    aliases_qs = RootAlias.objects.filter(owner=institution, root__in=chids_page).values_list('alias', 'root')
    alias_to_root = {alias: root for alias, root in aliases_qs}

    sp_qs = SystemProperty.objects.filter(owner=institution, value__in=alias_to_root.keys()).order_by('-created').values_list('value', 'uuid')
    latest_uuids = {}
    for alias, uuid in sp_qs:
        root = alias_to_root.get(alias)
        if root and root not in latest_uuids:
            latest_uuids[root] = uuid

    states_qs = State.objects.filter(snapshot_uuid__in=latest_uuids.values()).order_by('-date')
    uuid_to_state = {state.snapshot_uuid: state.state for state in states_qs}
    state_map = {root: str(uuid_to_state.get(uuid, "")) for root, uuid in latest_uuids.items()}

    return props_map, ben_map, default_ben_status, state_map

def build_bulk_device_export_dict(cache, state_str, ben_status_str, user_props_dict):
    """Standardizes dictionary construction."""
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
    dev_data["current_state"] = state_str
    dev_data["beneficiary_status"] = ben_status_str
    dev_data["user_properties"] = user_props_dict
    return dev_data

def build_device_response_list(chids_page, institution, lot=None):
    """Maps the bulk-fetched data directly to the Cache rows."""
    if not chids_page:
        return []

    cached_qs = ProductCache.objects.filter(owner=institution, root__in=chids_page)
    cache_map = {cache.root: cache for cache in cached_qs}

    props_map, ben_map, default_ben_status, state_map = fetch_bulk_device_data(chids_page, institution, lot)

    devices_export = []
    for root_id in chids_page:
        cache = cache_map.get(root_id)
        if cache:
            devices_export.append(build_bulk_device_export_dict(
                cache=cache,
                state_str=state_map.get(root_id, ""),
                ben_status_str=ben_map.get(root_id, default_ben_status),
                user_props_dict=props_map.get(root_id, {})
            ))
    return devices_export

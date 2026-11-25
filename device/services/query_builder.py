import logging
import operator
from functools import reduce

from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.expressions import RawSQL
from django.utils.translation import gettext_lazy as _

from django.db import connection
from device.product_cache import ProductCache
from evidence.models import UserProperty
from lot.models import DeviceBeneficiary, DeviceLot


logger = logging.getLogger('django')

class ProductQueryBuilder:
    UNASSIGNED_LOT_TOKEN = "__unassigned__"
    STANDARD_FIELDS = ['type', 'manufacturer', 'model', 'cpu_model']

    STATE_SQL = """
        SELECT s.state
        FROM action_state s
        INNER JOIN evidence_systemproperty sp ON s.snapshot_uuid = sp.uuid
        INNER JOIN evidence_rootalias ra ON sp.value = ra.alias
        WHERE ra.root = device_productcache.root
        ORDER BY s.date DESC
        LIMIT 1
    """

    def __init__(self, institution, request_get, allow_lot_filter=False):
        self.institution = institution
        self.request_get = request_get
        self.allow_lot_filter = allow_lot_filter

    def _clean_list(self, key, lower=False):
        vals = [v.strip() for v in self.request_get.getlist(key) if v.strip()]
        return [v.lower() for v in vals] if lower else vals

    def get_available_fields(self, base_chids):
        """Return the subset of STANDARD_FIELDS + DATA_FIELDS that have at least one
        non-empty value in the current device selection."""
        base_qs = ProductCache.objects.filter(owner=self.institution, root__in=base_chids)
        available = []

        for field in self.STANDARD_FIELDS:
            if base_qs.exclude(**{field: ''}).exclude(**{f"{field}__isnull": True}).exists() or self._clean_list(field):
                available.append(field)

        present_json_keys = set()
        non_empty_qs = base_qs.exclude(data={})
        if non_empty_qs.exists():
            sql, params = non_empty_qs.values_list('root', flat=True).query.sql_with_params()

            if connection.vendor == 'postgresql':
                query = f"""
                    SELECT DISTINCT kv.key
                    FROM device_productcache pc,
                         jsonb_each_text(pc.data::jsonb) AS kv(key, val)
                    WHERE pc.owner_id = %s
                      AND pc.root IN ({sql})
                      AND kv.val IS NOT NULL
                      AND BTRIM(kv.val) <> ''
                """
            elif connection.vendor == 'sqlite':
                logger.warning(
                    "Running ProductQueryBuilder.get_available_fields on SQLite; "
                    "JSON key extraction lacks GIN indexing and may degrade on large datasets."
                )
                query = f"""
                    SELECT DISTINCT kv.key
                    FROM device_productcache pc,
                         json_each(pc.data) AS kv
                    WHERE pc.owner_id = %s
                      AND pc.root IN ({sql})
                      AND kv.value IS NOT NULL
                      AND TRIM(CAST(kv.value AS TEXT)) <> ''
                """
            else:
                logger.warning(
                    "Unsupported DB vendor '%s' for JSON key SQL; falling back to Python scan.",
                    connection.vendor,
                )
                query = None

            if query:
                with connection.cursor() as cursor:
                    cursor.execute(query, [self.institution.pk, *params])
                    present_json_keys = {row[0] for row in cursor.fetchall()}
            else:
                for d in non_empty_qs.values_list('data', flat=True):
                    if isinstance(d, dict):
                        present_json_keys.update(
                            k for k, v in d.items()
                            if v is not None and str(v).strip() != ''
                        )

        for field in ProductCache.DATA_FIELDS:
            if field in present_json_keys or self._clean_list(field):
                available.append(field)

        return available

    def has_active_filter_params(self):
        if (self.request_get.get('lquery') or self.request_get.get('gquery') or '').strip():
            return True

        filter_keys = (
            self.STANDARD_FIELDS
            + list(ProductCache.DATA_FIELDS)
            + ['state', 'up_key', 'up_val', 'device_id', 'lot']
        )
        return any(bool(self._clean_list(k)) for k in filter_keys)

    def build_queryset(self, base_chids):
        """Builds a pure ORM QuerySet, annotated with current state and beneficiary status."""

        if hasattr(base_chids, 'query'):
            if not base_chids.query.values_select:
                base_chids = base_chids.values_list('root', flat=True)

        max_status = (
            DeviceBeneficiary.objects.filter(device_id=OuterRef('root'))
            .order_by('-status')
            .values('status')[:1]
        )

        qs = ProductCache.objects.filter(owner=self.institution, root__in=base_chids).annotate(
            current_state_annotated=RawSQL(self.STATE_SQL, []),
            beneficiary_status_annotated=Subquery(max_status),
        )
        if not self.has_active_filter_params():
            return qs

        # lot Filter
        if self.allow_lot_filter and (f_lots := self._clean_list('lot')):
            is_and = self.request_get.get('lot_op', 'or').strip().lower() == 'and'
            unassigned_tokens = {
                self.UNASSIGNED_LOT_TOKEN.lower(),
                "none",
                str(_("None")).strip().lower(),
            }
            base_lot_qs = DeviceLot.objects.filter(
                lot__owner=self.institution, device_id=OuterRef('root')
            )

            lot_conditions = [
                ~Exists(base_lot_qs)
                if val.lower() in unassigned_tokens
                else Exists(base_lot_qs.filter(lot__name__iexact=val))
                for val in f_lots
            ]
            qs = qs.filter(reduce(operator.and_ if is_and else operator.or_, lot_conditions))

        # device ID Filter
        if f_device_ids := self._clean_list('device_id', lower=True):
            id_q = reduce(
                operator.or_,
                (Q(root__icontains=v) | Q(shortid__icontains=v) for v in f_device_ids),
            )
            qs = qs.filter(id_q)

        # userProperty Key & Value Filters
        user_prop_base = UserProperty.objects.filter(
            owner=self.institution,
            device_id=OuterRef('root'),
            type=UserProperty.Type.USER,
        )

        if f_up_keys := self._clean_list('up_key'):
            key_q = reduce(operator.or_, (Q(key__icontains=k) for k in f_up_keys))
            qs = qs.filter(Exists(user_prop_base.filter(key_q)))

        if f_up_vals := self._clean_list('up_val'):
            val_q = reduce(operator.or_, (Q(value__icontains=v) for v in f_up_vals))
            qs = qs.filter(Exists(user_prop_base.filter(val_q)))

        # standard & JSON `data` Columns
        for field in self.STANDARD_FIELDS:
            if vals := self._clean_list(field):
                qs = qs.filter(reduce(operator.or_, (Q(**{f"{field}__icontains": v}) for v in vals)))

        for field in ProductCache.DATA_FIELDS:
            if vals := self._clean_list(field, lower=True):
                qs = qs.filter(
                    reduce(operator.or_, (Q(**{f"data__{field}__icontains": v}) for v in vals))
                )

        # global Search Bar (`lquery` / `gquery`)
        global_query = (self.request_get.get('lquery') or self.request_get.get('gquery') or '').strip().lower()
        if global_query:
            search_fields = ('manufacturer', 'type', 'model', 'cpu_model', 'shortid', 'serial', 'root')
            field_q = reduce(operator.or_, (Q(**{f"{f}__icontains": global_query}) for f in search_fields))
            prop_q = Exists(
                user_prop_base.filter(Q(key__icontains=global_query) | Q(value__icontains=global_query))
            )
            qs = qs.filter(field_q | prop_q)

        # state Filter
        if f_states := self._clean_list('state', lower=True):
            state_q = reduce(operator.or_, (Q(current_state_annotated__iexact=s) for s in f_states))
            qs = qs.filter(state_q)

        return qs

    def get_paginated_queryset(self, base_chids, limit=10, page=1, sort_param='-last_updated'):
        """Sorts the annotated queryset and returns a native Django Paginator Page."""
        qs = self.build_queryset(base_chids)

        prefix = '-' if sort_param.startswith('-') else ''
        sort_field = sort_param.lstrip('-')

        sort_map = {
            'type': 'type',
            'manufacturer': 'manufacturer',
            'model': 'model',
            'last_updated': 'last_updated',
            'shortid': 'shortid',
            'current_state': 'current_state_annotated',
            'status_beneficiary': 'beneficiary_status_annotated',
        }

        if target_field := sort_map.get(sort_field):
            qs = qs.order_by(f"{prefix}{target_field}", 'root')
        else:
            qs = qs.order_by('-last_updated', '-pk')

        if limit == 0:
            return qs

        return Paginator(qs, limit).get_page(page)

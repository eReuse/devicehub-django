# State redesign, step 2/3: data migration.
#
# Moves State from one row per state change anchored on snapshot_uuid to
# one row per (institution, root) anchored on RootAlias.root:
#
# 1. Every institution without StateDefinitions gets the minimal INBOX.
# 2. For every legacy row, snapshot_uuid -> SystemProperty.value (same
#    owner) -> RootAlias.root, and the state name -> StateDefinition. The
#    newest legacy row per (institution, root) wins, which is what the
#    product page (Device.get_current_state) showed.
# 3. Every distinct root in RootAlias gets a row: the legacy state if any,
#    otherwise the institution's first state by order, dated when the
#    root first appeared (so a later real change wins on a merge).
# 4. Every merged alias (alias != root) gets a dormant row with its own
#    newest legacy state (only its own evidences) or the default, so that
#    splitting it later restores its previous state. Afterwards every
#    RootAlias.alias and every root has exactly one State row.
# 5. Legacy rows are deleted; 0006 drops their columns.
#
# Legacy rows that can't be resolved (no institution, unknown state name,
# uuid without SystemProperty/RootAlias) fall back to the default state of
# their roots and are counted in the report printed at the end.

from collections import Counter

from django.db import migrations
from django.db.models import F, Min

# Hard-coded on purpose: migrations must not depend on app code that may
# change later (same value as action.models.INITIAL_STATE).
INITIAL_STATE = "INBOX"
BATCH = 2000


def chunks(iterable, size):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def ensure_initial_states(Institution, StateDefinition, report):
    with_states = set(
        StateDefinition.objects.values_list("institution_id", flat=True).distinct()
    )
    for inst_id in Institution.objects.exclude(pk__in=with_states).values_list("pk", flat=True):
        StateDefinition.objects.create(
            institution_id=inst_id, state=INITIAL_STATE, order=1
        )
        report["institutions given INBOX"] += 1


def legacy_states(State, StateDefinition, SystemProperty, RootAlias, report):
    """Newest legacy state as (date, sd_id, user_id), keyed by
    (institution_id, root) and by (institution_id, alias)."""
    sd_by_name = {
        (sd["institution_id"], sd["state"]): sd["pk"]
        for sd in StateDefinition.objects.values("pk", "institution_id", "state")
    }
    best = {}
    best_alias = {}
    legacy = (
        State.objects.filter(root__isnull=True)
        .order_by("date", "pk")
        .values("institution_id", "user_id", "date", "state", "snapshot_uuid")
    )
    for rows in chunks(legacy.iterator(chunk_size=BATCH), BATCH):
        uuids = {r["snapshot_uuid"] for r in rows}
        values_by_uuid = {}
        for sp in SystemProperty.objects.filter(uuid__in=uuids).values("owner_id", "uuid", "value"):
            values_by_uuid.setdefault((sp["owner_id"], sp["uuid"]), set()).add(sp["value"])
        aliases = set().union(*values_by_uuid.values()) if values_by_uuid else set()
        root_by_alias = {}
        for ra in RootAlias.objects.filter(alias__in=aliases).values("owner_id", "alias", "root"):
            root_by_alias[(ra["owner_id"], ra["alias"])] = ra["root"]

        for r in rows:
            inst = r["institution_id"]
            if inst is None:
                report["legacy rows without institution"] += 1
                continue
            sd = sd_by_name.get((inst, r["state"]))
            if sd is None:
                report["legacy rows with unknown state name"] += 1
                continue
            aliases = [
                v for v in values_by_uuid.get((inst, r["snapshot_uuid"]), ())
                if (inst, v) in root_by_alias
            ]
            if not aliases:
                report["legacy rows with unresolved uuid"] += 1
                continue
            # Ordered by date ascending: newer rows overwrite older ones.
            value = (r["date"], sd, r["user_id"])
            for alias in aliases:
                best_alias[(inst, alias)] = value
                best[(inst, root_by_alias[(inst, alias)])] = value
    return best, best_alias


def forwards(apps, schema_editor):
    Institution = apps.get_model("user", "Institution")
    StateDefinition = apps.get_model("action", "StateDefinition")
    State = apps.get_model("action", "State")
    RootAlias = apps.get_model("evidence", "RootAlias")
    SystemProperty = apps.get_model("evidence", "SystemProperty")

    report = Counter()
    report["legacy rows"] = State.objects.filter(root__isnull=True).count()

    ensure_initial_states(Institution, StateDefinition, report)
    best, best_alias = legacy_states(State, StateDefinition, SystemProperty, RootAlias, report)

    default_sd = {}
    for sd in StateDefinition.objects.order_by("institution_id", "order", "pk").values("pk", "institution_id"):
        default_sd.setdefault(sd["institution_id"], sd["pk"])

    roots = (
        RootAlias.objects.values("owner_id", "root")
        .annotate(first_seen=Min("created"))
        .order_by("owner_id", "root")
    )
    for batch in chunks(roots.iterator(chunk_size=BATCH), BATCH):
        new_rows = []
        for r in batch:
            inst, root = r["owner_id"], r["root"]
            legacy = best.get((inst, root))
            if legacy:
                date, sd, user = legacy
                report["roots with legacy state"] += 1
            else:
                date, sd, user = r["first_seen"], default_sd[inst], None
                report["roots with default state"] += 1
            new_rows.append(State(
                institution_id=inst, root=root, state_definition_id=sd,
                user_id=user, date=date,
            ))
        State.objects.bulk_create(new_rows, batch_size=BATCH)

    merged = (
        RootAlias.objects.exclude(alias=F("root"))
        .values("owner_id", "alias", "created")
        .order_by("owner_id", "alias")
    )
    for batch in chunks(merged.iterator(chunk_size=BATCH), BATCH):
        new_rows = []
        for r in batch:
            inst, alias = r["owner_id"], r["alias"]
            legacy = best_alias.get((inst, alias))
            if legacy:
                date, sd, user = legacy
                report["dormant aliases with legacy state"] += 1
            else:
                date, sd, user = r["created"], default_sd[inst], None
                report["dormant aliases with default state"] += 1
            new_rows.append(State(
                institution_id=inst, root=alias, state_definition_id=sd,
                user_id=user, date=date,
            ))
        State.objects.bulk_create(new_rows, batch_size=BATCH)

    State.objects.filter(root__isnull=True).delete()

    print()
    for key in sorted(report):
        print(f"    state migration: {key}: {report[key]}")


def backwards(apps, schema_editor):
    apps.get_model("action", "State").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("action", "0004_state_root_state_definition"),
        ("evidence", "0013_credentialproperty_and_more"),
        ("user", "0001_initial"),
    ]

    # The legacy rows can't be rebuilt (several collapse into one row per
    # root), so going backwards just empties the table: states are lost.
    operations = [
        migrations.RunPython(forwards, backwards),
    ]

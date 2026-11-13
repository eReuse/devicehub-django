"""Keep the entry state from undoing progress when two products join.

Every new root gets the entry state (``order=1``, see
``evidence.models.ensure_root_alias_self_reference``). A Workbench snapshot of
a phone that was registered with the web form is such a new root until
``link_custom_id`` joins it to the label's product. Its entry state is then
the newest row of the joined product and would send it back to the entry
state, although the product had already moved on.
"""
from action.models import State, StateDefinition


def _uuids_of_values(owner, values):
    from evidence.models import SystemProperty

    return SystemProperty.objects.filter(owner=owner, value__in=values).values_list(
        "uuid", flat=True
    )


def drop_redundant_entry_states(owner, alias, new_root):
    """After ``alias`` joins ``new_root``, drop the side that only holds entry states.

    If both sides have moved on, both histories are kept.
    """
    from evidence.models import RootAlias

    definition = StateDefinition.objects.filter(institution=owner, order=1).first()
    if not definition:
        return

    joining = set(_uuids_of_values(owner, [alias]))
    product = set(_uuids_of_values(owner, RootAlias.physical_aliases(owner, new_root)))
    joining_states = State.objects.filter(institution=owner, snapshot_uuid__in=joining)
    product_states = State.objects.filter(
        institution=owner, snapshot_uuid__in=product - joining
    )
    if not joining_states.exists() or not product_states.exists():
        return

    def only_entry(states):
        return not states.exclude(state=definition.state).exists()

    for side, other in ((joining_states, product_states), (product_states, joining_states)):
        if only_entry(side) and not only_entry(other):
            side.delete()
            return

"""Contributor role: a user who only sees the products they registered.

A product belongs to a contributor when at least one of its evidences was
uploaded by them (``SystemProperty.user``). See ereuse/projectes#965.
"""
from django.http import Http404

from evidence.models import RootAlias, SystemProperty


def is_restricted(user):
    return bool(getattr(user, "is_contributor", False)) and not user.is_admin


def visible_roots(user):
    """Canonical roots ``user`` may see, or None when unrestricted."""
    if not is_restricted(user):
        return None
    institution = user.institution
    mine = SystemProperty.objects.filter(
        owner=institution, user=user).values("value")
    return (RootAlias.objects.filter(owner=institution, alias__in=mine)
            .values("root").distinct())


def restrict_roots(qry, user):
    """Narrow a queryset of ``{"root": ...}`` rows to what ``user`` may see."""
    roots = visible_roots(user)
    if roots is None:
        return qry
    return qry.filter(root__in=roots)


def can_see(user, device_id):
    roots = visible_roots(user)
    if roots is None:
        return True
    root = RootAlias.resolve_root(user.institution, device_id)
    return roots.filter(root=root).exists()


def check_can_see(user, device_id):
    if not can_see(user, device_id):
        raise Http404

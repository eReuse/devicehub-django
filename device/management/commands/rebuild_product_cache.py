#!/usr/bin/env python3
import logging

from django.core.management.base import BaseCommand, CommandError

from user.models import Institution
from device.models import ProductCache

logger = logging.getLogger('django')


class Command(BaseCommand):
    help = (
        "Rebuild the ProductCache read model from evidence. Idempotent: "
        "safe to run any time to reconcile the cache with current "
        "evidence and RootAlias state. Reads evidence (Xapian) but never "
        "writes to it; only the ProductCache table is modified."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner',
            type=int,
            default=None,
            help='Institution id to scope the rebuild to (default: all).',
        )

    def handle(self, *args, **options):
        owner = None
        owner_id = options.get('owner')
        if owner_id is not None:
            owner = Institution.objects.filter(pk=owner_id).first()
            if not owner:
                raise CommandError(f'No institution with id {owner_id}')

        total = ProductCache.rebuild_all(owner=owner)

        scope = owner.name if owner else 'all institutions'
        self.stdout.write(self.style.SUCCESS(
            f'Rebuilt {total} product cache(s) for {scope}.'
        ))

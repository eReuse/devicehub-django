from django.core.management.base import BaseCommand, CommandError

from user.models import Institution
from lot.models import LotTag, Lot


class Command(BaseCommand):
    help = "Create demo lots for stress-testing pagination and UI layout"

    def add_arguments(self, parser):
        parser.add_argument('institution', type=str, help='Institution name')
        parser.add_argument(
            'count', type=int, nargs='?', default=200,
            help='Number of lots to create (default: 200)',
        )

    def handle(self, *args, **kwargs):
        name = kwargs['institution']
        count = kwargs['count']
        if count < 1:
            raise CommandError("count must be a positive integer.")
        try:
            institution = Institution.objects.get(name=name)
        except Institution.DoesNotExist:
            raise CommandError(f"Institution '{name}' not found.")

        tags = {
            t.name: t
            for t in LotTag.objects.filter(owner=institution, name__in=["Entrada", "Salida", "Temporal"])
        }
        missing = [n for n in ("Entrada", "Salida", "Temporal") if n not in tags]
        if missing:
            raise CommandError(
                f"Missing lot tags for institution '{name}': {', '.join(missing)}. "
                "Run 'add_institution' first."
            )

        per_tag = count // 3
        entrada_count = per_tag
        salida_count = per_tag
        temporal_count = count - 2 * per_tag  # absorbs the remainder

        lots = []

        for i in range(1, entrada_count + 1):
            lots.append(Lot(
                name=f"donante-{i:03d}",
                owner=institution,
                type=tags["Entrada"],
                archived=(i % 10 == 0),
            ))

        for i in range(1, salida_count + 1):
            lots.append(Lot(
                name=f"beneficiario-{i:03d}",
                owner=institution,
                type=tags["Salida"],
                archived=(i % 10 == 0),
            ))

        for i in range(1, temporal_count + 1):
            lots.append(Lot(
                name=f"palet-{i:03d}",
                owner=institution,
                type=tags["Temporal"],
                archived=(i % 10 == 0),
            ))

        Lot.objects.bulk_create(lots)
        self.stdout.write(
            self.style.SUCCESS(f"Created {len(lots)} lots for institution '{name}'.")
        )

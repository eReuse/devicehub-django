# Creates bulk beneficiaries in a specific lot for stress-testing the beneficiary paginator.
# Usage:
#   python manage.py add_demo_beneficiaries <institution> <lot_name> <shop_email> [count]
#
# Examples:
#   python manage.py add_demo_beneficiaries example-org "beneficiario-org1" user@example.org
#   python manage.py add_demo_beneficiaries example-org "beneficiario-org1" user@example.org 200
#
# The command will get-or-create a SHOP subscription for the given user+lot, then
# bulk-create <count> beneficiaries (default 100) with emails beneficiary-001@example.org,
# beneficiary-002@example.org, ... which is enough to verify multi-page pagination (25/page).

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from lot.models import Lot, LotSubscription, Beneficiary
from user.models import Institution


User = get_user_model()


class Command(BaseCommand):
    help = "Create demo beneficiaries in a lot to stress-test the beneficiary paginator"

    def add_arguments(self, parser):
        parser.add_argument('institution', type=str, help='Institution name')
        parser.add_argument('lot', type=str, help='Lot name within the institution')
        parser.add_argument('shop_email', type=str, help='Email of the shop user (must exist)')
        parser.add_argument(
            'count', type=int, nargs='?', default=100,
            help='Number of beneficiaries to create (default: 100)',
        )

    def handle(self, *args, **kwargs):
        institution_name = kwargs['institution']
        lot_name = kwargs['lot']
        shop_email = kwargs['shop_email']
        count = kwargs['count']

        if count < 1:
            raise CommandError("count must be a positive integer.")

        try:
            institution = Institution.objects.get(name=institution_name)
        except Institution.DoesNotExist:
            raise CommandError(f"Institution '{institution_name}' not found.")

        try:
            lot = Lot.objects.get(name=lot_name, owner=institution)
        except Lot.DoesNotExist:
            raise CommandError(f"Lot '{lot_name}' not found in institution '{institution_name}'.")

        try:
            shop_user = User.objects.get(email=shop_email, institution=institution)
        except User.DoesNotExist:
            raise CommandError(f"User '{shop_email}' not found in institution '{institution_name}'.")

        shop_sub, _ = LotSubscription.objects.get_or_create(
            lot=lot,
            user=shop_user,
            defaults={'type': LotSubscription.Type.SHOP},
        )

        beneficiaries = [
            Beneficiary(
                email=f"beneficiary-{i:03d}@example.org",
                lot=lot,
                shop=shop_sub,
            )
            for i in range(1, count + 1)
        ]
        Beneficiary.objects.bulk_create(beneficiaries)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {count} beneficiaries in lot '{lot_name}' "
                f"under shop '{shop_email}' (institution '{institution_name}')."
            )
        )

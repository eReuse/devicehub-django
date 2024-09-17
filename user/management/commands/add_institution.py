from django.core.management.base import BaseCommand
from user.models import Institution


class Command(BaseCommand):
    help = "Create a new Institution"

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='institution')

    def handle(self, *args, **kwargs):
        Institution.objects.create(name=kwargs['name'])

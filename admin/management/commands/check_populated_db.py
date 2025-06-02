from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Check if Devicehub\'s DB has been populated already. '

    def handle(self, *args, **options):
        #check if at least one migration has been applied
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM django_migrations LIMIT 1")
                if cursor.fetchone():
                    return 0
        except:
            return 1
        return 1

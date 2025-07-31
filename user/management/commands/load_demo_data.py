from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from user.models import Institution


User = get_user_model()


class Command(BaseCommand):
    help = "Create user for test"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **kwargs):
        self.institution = Institution.objects.first()
        self.password = "1234"
        users = [
            "donor@example.org",
            "circuit-manager@example.org",
            "shop@example.org",
            "beneficiary@example.org",
        ]

        for email in users:
            self.create_user(email)

    def create_user(self, email):
        User.objects.create_user(
            institution=self.institution,
            email=email,
            password=self.password,
        )

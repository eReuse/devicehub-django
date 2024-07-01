from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


User = get_user_model()


class Command(BaseCommand):
    help = "Create a new user"

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='email')
        parser.add_argument('password', type=str, help='password')

    def handle(self, *args, **kwargs):
        email = kwargs['email']
        password = kwargs['password']
        self.create_user(email, password)

    def create_user(self, email, password):
        u = User.objects.create(email=email, password=password)
        u.set_password(password)
        u.save()

from uuid import uuid4

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from user.models import Institution
from api.models import  Token


User = get_user_model()


class Command(BaseCommand):
    help = "Create a new user"

    def add_arguments(self, parser):
        parser.add_argument('institution', type=str, help='institution')
        parser.add_argument('email', type=str, help='email')
        parser.add_argument('password', type=str, help='password')

    def handle(self, *args, **kwargs):
        self.email = kwargs['email']
        self.password = kwargs['password']
        self.institution = Institution.objects.get(name=kwargs['institution'])
        self.create_user()

    def create_user(self):
        self.u = User.objects.create(
            institution=self.institution,
            email=self.email,
            password=self.password
        )
        self.u.set_password(self.password)
        self.u.save()
        token = uuid4()
        Token.objects.create(token=token, owner=self.u)
        print(f"TOKEN: {token}")

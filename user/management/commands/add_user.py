from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from lot.models import LotTag
from user.models import Institution


User = get_user_model()


class Command(BaseCommand):
    help = "Create a new user"

    def add_arguments(self, parser):
        parser.add_argument('institution', type=str, help='institution')
        parser.add_argument('email', type=str, help='email')
        parser.add_argument('password', type=str, help='password')
        parser.add_argument('is_admin', nargs='?', default=False, type=str, help='is admin')

    def handle(self, *args, **kwargs):
        email = kwargs['email']
        password = kwargs['password']
        is_admin = kwargs['is_admin']
        institution = Institution.objects.get(name=kwargs['institution'])
        self.create_user(institution, email, password, is_admin)
        self.create_lot_tags()

    def create_user(self, institution, email, password, is_admin):
        self.u = User.objects.create(
            institution=institution,
            email=email,
            password=password,
            is_admin=is_admin,
        )
        self.u.set_password(password)
        self.u.save()

    def create_lot_tags(self):
        tags = [
            "Entrada",
            "Salida",
            "Temporal"
        ]
        for tag in tags:
            LotTag.objects.create(
                name=tag,
                owner=self.u.institution,
                user=self.u
            )

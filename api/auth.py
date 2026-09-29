import logging

from django.core.exceptions import ValidationError
from ninja.security import HttpBearer
from api.models import Token


logger = logging.getLogger('django')


class GlobalAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            tk = Token.objects.filter(token=token).first()
        except (ValueError, ValidationError):
            return None
        if tk and tk.is_active:
            return tk.owner

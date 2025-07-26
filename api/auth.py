import logging

from ninja.security import HttpBearer
from api.models import Token


logger = logging.getLogger('django')


class GlobalAuth(HttpBearer):
    def authenticate(self, request, token):
        tk = Token.objects.filter(token=token).first()
        if tk and tk.is_active:
            return tk.owner

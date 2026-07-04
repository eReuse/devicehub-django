import logging

from ninja.security import HttpBearer
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
from api.models import Token

logger = logging.getLogger('django')

class GlobalAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            clean_token = token.strip()
            tk = Token.objects.filter(token=clean_token).first()
            if tk and tk.is_active:
                return tk.owner
        except (ValueError, ValidationError) as e:
            logger.warning("Malformed Token: %s", str(e))
        except Exception as e:
            logger.warning("Unexpected error with token:: %s", str(e))

        raise HttpError(401, "Malformed, invalid or not active token")

import logging

from uuid import UUID

from ninja.security import HttpBearer

from api.models import Token

logger = logging.getLogger('django')


class GlobalAuth(HttpBearer):
    def authenticate(self, request, token):
        # Token.token is a UUIDField: a non-UUID lookup raises ValidationError
        try:
            token_uuid = UUID(token.strip())
        except ValueError:
            logger.warning("Rejected API request with malformed token")
            return None

        tk = Token.objects.filter(token=token_uuid).first()
        if tk and tk.is_active:
            return tk.owner

        logger.warning("Rejected API request with invalid or inactive token")
        return None

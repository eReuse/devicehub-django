import uuid as uuidlib

from api.tests.base import ApiTestCase

URL = "/api/v1/devices/"


class AuthTest(ApiTestCase):

    def test_valid_token_is_accepted(self):
        response = self.client.get(URL, **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_request_without_token_is_rejected(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 401)

    def test_unknown_token_is_rejected(self):
        response = self.client.get(
            URL, HTTP_AUTHORIZATION=f"Bearer {uuidlib.uuid4()}")
        self.assertEqual(response.status_code, 401)

    def test_inactive_token_is_rejected(self):
        token = self.make_token(self.user, is_active=False)
        response = self.client.get(URL, **self.bearer(token))
        self.assertEqual(response.status_code, 401)

    def test_malformed_token_is_rejected_instead_of_crashing(self):
        """Token.token is a UUIDField, so a non-UUID reaching the lookup raises
        ValidationError and would surface as a 500."""
        response = self.client.get(URL, HTTP_AUTHORIZATION="Bearer not-a-uuid")
        self.assertEqual(response.status_code, 401)

    def test_empty_bearer_is_rejected(self):
        response = self.client.get(URL, HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(response.status_code, 401)

    def test_wrong_scheme_is_rejected(self):
        response = self.client.get(
            URL, HTTP_AUTHORIZATION=f"Basic {self.token.token}")
        self.assertEqual(response.status_code, 401)

    def test_surrounding_whitespace_is_tolerated(self):
        response = self.client.get(
            URL, HTTP_AUTHORIZATION=f"Bearer {self.token.token} ")
        self.assertEqual(response.status_code, 200)

    def test_error_payload_follows_the_message_schema(self):
        response = self.client.get(URL, HTTP_AUTHORIZATION="Bearer not-a-uuid")
        self.assertEqual(
            response.json(),
            {"error": "Unauthorized",
             "details": "Malformed, invalid or not active token"},
        )

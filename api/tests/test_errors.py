from api.tests.base import ApiTestCase


class ErrorShapeTest(ApiTestCase):
    """Every error must come back as MessageOut, whichever path raised it."""

    def setUp(self):
        super().setUp()
        self.root = self.device_root("a" * 12)
        self.make_device(self.root)

    def assertMessageOut(self, response, status_code, error):
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertEqual(sorted(body), ["details", "error"])
        self.assertEqual(body["error"], error)
        self.assertIsInstance(body["details"], str)

    def test_http_error_is_formatted(self):
        response = self.client.get(
            f"/api/v1/devices/{self.device_root('nope')}/properties/k/", **self.auth)
        self.assertMessageOut(response, 404, "Not Found")

    def test_object_not_found_is_formatted(self):
        """get_object_or_404 raises Http404, which bypasses the HttpError handler."""
        response = self.client.get(
            f"/api/v1/devices/{self.root}/properties/missing/", **self.auth)
        self.assertMessageOut(response, 404, "Not Found")

    def test_both_not_found_paths_share_the_same_shape(self):
        by_device = self.client.get(
            f"/api/v1/devices/{self.device_root('nope')}/properties/k/", **self.auth)
        by_property = self.client.get(
            f"/api/v1/devices/{self.root}/properties/missing/", **self.auth)
        self.assertEqual(sorted(by_device.json()), sorted(by_property.json()))

    def test_schema_validation_error_is_formatted(self):
        response = self.client.post(
            f"/api/v1/devices/{self.root}/properties/k/", {"value": ""},
            content_type="application/json", **self.auth)
        self.assertMessageOut(response, 422, "Unprocessable Entity")
        self.assertIn("value", response.json()["details"])

    def test_authentication_error_is_formatted(self):
        response = self.client.get("/api/v1/devices/")
        self.assertMessageOut(response, 401, "Unauthorized")

    def test_business_error_is_formatted(self):
        response = self.client.post(
            "/api/v1/devices/bulk-properties/",
            {"device_ids": ["INVALID"], "key": "k", "value": "v"},
            content_type="application/json", **self.auth)
        self.assertMessageOut(response, 422, "Unprocessable Entity")

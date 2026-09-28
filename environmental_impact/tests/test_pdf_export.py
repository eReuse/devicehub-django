import importlib.util
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from environmental_impact.pdf import PdfUnavailable, _css_string, render_lot_report_pdf, report_filename
from environmental_impact.tests.test_lot_presenters import LotPresenterTests

HAS_WEASYPRINT = importlib.util.find_spec("weasyprint") is not None


class PdfHelpersTests(SimpleTestCase):
    def test_filename_is_slugged_and_dated(self):
        self.assertEqual(
            report_filename("supplier", "Donación Empresa Ejemplo 2026", date(2026, 9, 28)),
            "impact-supplier-donacion-empresa-ejemplo-2026-2026-09-28.pdf",
        )
        self.assertEqual(report_filename("recipient", "", date(2026, 1, 2)), "impact-recipient-lot-2026-01-02.pdf")

    def test_footer_text_cannot_break_the_css_string(self):
        self.assertEqual(_css_string('Lot "A" \\ <b>x</b>'), "Lot A  bx/b")


class PdfExportTests(LotPresenterTests):
    """Renders each report view to a real PDF (skipped without WeasyPrint)."""

    def request(self):
        request = RequestFactory().get("/lot/1/environmental-impact", {"format": "pdf"})
        request.user = SimpleNamespace(institution=SimpleNamespace(name="Pangea"))
        return request

    @unittest.skipUnless(HAS_WEASYPRINT, "WeasyPrint not installed")
    def test_every_view_exports_a_pdf(self):
        for view in ("supplier", "recipient", "refurbisher"):
            response = render_lot_report_pdf(self.request(), self.view(view=view), "Pangea")
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"), view)
            self.assertIn(f'filename="impact-{view}-l1-', response["Content-Disposition"])

    def test_missing_weasyprint_raises_a_clear_error(self):
        with patch.dict("sys.modules", {"weasyprint": None}):
            with self.assertRaises(PdfUnavailable):
                render_lot_report_pdf(self.request(), self.view(view="supplier"), "Pangea")


class DevicePdfExportTests(SimpleTestCase):
    """The device tab as a PDF, for a reused, a pending and a no-reading device."""

    def v2(self, points, reuse_start=0):
        from datetime import datetime
        from environmental_impact.algorithms.ereuse2026.ereuse2026 import load_factors, load_grid
        from environmental_impact.algorithms.ereuse2026.model import DeviceInputs, EvidencePoint, compute_device
        from environmental_impact.presenters import device_impact_view

        inputs = DeviceInputs(
            device_type="laptop",
            points=[EvidencePoint(f"e{i}", datetime(2025, 1 + i, 1), h) for i, h in enumerate(points)],
            country="ES", reuse_start=reuse_start,
            reuse_source="second_evidence" if reuse_start is not None else None,
            detected_start=reuse_start, detected_source="second_evidence" if reuse_start is not None else None,
            bios_year=2018,
        )
        return device_impact_view(compute_device(inputs, load_factors(), load_grid()), inputs, set())

    def device(self):
        return SimpleNamespace(id="ereuse24:abcdef123", shortid="ABCDEF", manufacturer="Lenovo", model="X260")

    def test_reused_device_states_car_equivalence(self):
        v2 = self.v2([4439, 4448])
        self.assertGreater(v2["avoided_car_km"], 0)
        self.assertEqual(v2["avoided_car_km"] % 10, 0)  # rounded: an order of magnitude, not a measurement

    def test_filename_uses_the_short_id(self):
        from environmental_impact.pdf import device_report_filename
        self.assertEqual(device_report_filename("ABCDEF", date(2026, 9, 28)), "impact-device-abcdef-2026-09-28.pdf")

    @unittest.skipUnless(HAS_WEASYPRINT, "WeasyPrint not installed")
    def test_device_exports_a_pdf(self):
        from environmental_impact.pdf import render_device_report_pdf
        request = RequestFactory().get("/device/x/", {"format": "pdf"})
        for points, start in (([4439, 4448], 0), ([720], None), ([0], 0)):
            response = render_device_report_pdf(request, self.v2(points, start), self.device(), "Pangea")
            self.assertTrue(response.content.startswith(b"%PDF"), points)
            self.assertIn('filename="impact-device-abcdef-', response["Content-Disposition"])

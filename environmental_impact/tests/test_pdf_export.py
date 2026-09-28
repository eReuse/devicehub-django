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

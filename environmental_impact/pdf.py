"""PDF export of the lot impact reports (WeasyPrint).

The PDF uses its own A4 template (``reports/lot_report_pdf.html``) fed with the
same view data as the lot page, so the figures in the file and on screen always
come from the same calculation.
"""

from __future__ import annotations

import re

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

TITLES = {
    "supplier": (_("Impact report · supplier"), _("Devices from %(who)s")),
    "recipient": (_("Impact report · recipient"), _("Refurbished devices delivered to %(who)s")),
    "refurbisher": (_("Impact report · refurbisher"), _("Lot %(lot)s")),
}


class PdfUnavailable(RuntimeError):
    """WeasyPrint (or its system libraries) is not installed."""


def _css_string(text: str) -> str:
    """Safe inside a CSS ``content: "..."`` string: no quotes, backslashes or tags."""
    return re.sub(r'["\\<>]', "", text)[:120]


def report_filename(view: str, lot_name: str, issued) -> str:
    return f"impact-{view}-{slugify(lot_name) or 'lot'}-{issued:%Y-%m-%d}.pdf"


def render_lot_report_pdf(request, lv: dict, institution_name: str) -> HttpResponse:
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as err:  # OSError: missing Pango/Cairo libraries
        raise PdfUnavailable(str(err)) from err

    issued = timezone.now().date()  # works with USE_TZ on or off
    view = lv["view"]
    eyebrow, heading = (str(t) for t in TITLES.get(view, TITLES["refurbisher"]))
    heading = heading % {"who": lv["prepared_for"] or lv["lot_name"], "lot": lv["lot_name"]}
    html = render_to_string(
        "reports/lot_report_pdf.html",
        {
            "lv": lv,
            "title": f"{eyebrow} · {lv['lot_name']}",
            "eyebrow": eyebrow,
            "heading": heading,
            "institution_name": institution_name,
            "issued": issued,
            "footer_left": _css_string(f"{institution_name} · {lv['lot_name']} · {lv['lot'].method_version}"),
        },
        request=request,
    )
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{report_filename(view, lv["lot_name"], issued)}"'
    return response


def device_report_filename(shortid: str, issued) -> str:
    return f"impact-device-{slugify(shortid) or 'device'}-{issued:%Y-%m-%d}.pdf"


def render_device_report_pdf(request, v2: dict, device, institution_name: str) -> HttpResponse:
    """The device's environmental impact tab as an A4 PDF, from the same view data."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as err:  # OSError: missing Pango/Cairo libraries
        raise PdfUnavailable(str(err)) from err

    issued = timezone.now().date()
    shortid = getattr(device, "shortid", "") or str(device.id)
    name = " ".join(x for x in (device.manufacturer, device.model) if x) or shortid
    html = render_to_string(
        "reports/device_report_pdf.html",
        {
            "v2": v2,
            "i": v2["impact"],
            "title": f"{_('Impact report · device')} · {shortid}",
            "device_name": name,
            "device_shortid": shortid,
            "device_id": device.id,
            "institution_name": institution_name,
            "issued": issued,
            "footer_left": _css_string(f"{institution_name} · {shortid} · {v2['impact'].method_version}"),
        },
        request=request,
    )
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{device_report_filename(shortid, issued)}"'
    return response

from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from environmental_impact.algorithms.ereuse2026.ereuse2026 import load_factors, load_grid
from environmental_impact.algorithms.ereuse2026.model import (
    DeviceInputs,
    EvidencePoint,
    aggregate_lot,
    compute_device,
)
from environmental_impact.lot_presenters import default_view, kg, lot_impact_view


def impact(points, reuse_start=0, end_of_life=False):
    inputs = DeviceInputs(
        device_type="desktop",
        points=[EvidencePoint(f"e{i}", datetime(2024, 1 + i, 1), h) for i, h in enumerate(points)],
        country="ES",
        reuse_start=reuse_start,
        reuse_source="outgoing_lot" if reuse_start is not None else None,
        end_of_life=end_of_life,
    )
    return compute_device(inputs, load_factors(), load_grid())


def device(n):
    return SimpleNamespace(id=f"ereuse24:{n}", shortid=f"ABC{n}", manufacturer="Dell", model="OptiPlex 7010")


class LotPresenterTests(SimpleTestCase):
    def setUp(self):
        self.impacts = [
            impact([3696, 9439]),                                # reused, measured second life
            impact([9000], reuse_start=None, end_of_life=True),  # recycled
            impact([720], reuse_start=None),                     # still in the workshop
        ]
        self.rows = [(device(i), d) for i, d in enumerate(self.impacts)]
        self.lot = aggregate_lot(self.impacts)

    def view(self, tag="Entrada", view=None):
        return lot_impact_view(self.lot, self.rows, tag_name=tag, view=view, prepared_for="rsc@example.org", lot_name="L1")

    def test_default_view_follows_the_lot_tag(self):
        self.assertEqual(default_view("Entrada"), "supplier")
        self.assertEqual(default_view("Salida"), "recipient")
        self.assertEqual(default_view("Temporal"), "refurbisher")
        self.assertEqual(default_view(None), "refurbisher")

    def test_operator_can_pick_any_view(self):
        self.assertEqual(self.view("Entrada", "recipient")["view"], "recipient")
        self.assertEqual(self.view("Entrada", "nonsense")["view"], "supplier")

    def test_recycling_credit_is_drawn_below_zero(self):
        stages = {s["key"]: s for s in self.view()["stages"]}
        self.assertLess(stages["end_of_life"]["value"], 0)
        self.assertGreater(stages["end_of_life"]["down"], 0)
        self.assertEqual(stages["end_of_life"]["up"], 0)

    def test_rows_list_reused_first(self):
        self.assertEqual([r["status"] for r in self.view()["rows"]], ["reused", "recycled", "pending"])

    def test_wording_uses_the_lot_figures(self):
        view = self.view()
        self.assertIn(kg(self.lot.avoided), view["supplier_ok"][0])
        self.assertEqual(view["supplier_ok"][1], "1 device was sent to recycling.")
        self.assertIn("1 was refurbished and reused", view["supplier_ok"][0])
        self.assertIn(kg(self.lot.attributed_kg), view["recipient_ok"][0])

    def test_kg_switches_to_tonnes(self):
        self.assertEqual(kg(950), "950 kg")
        self.assertEqual(kg(5421), "5.4 t")
        self.assertEqual(kg(None), "—")


class LotTemplateTests(LotPresenterTests):
    """The three views render with a real request context."""

    def render(self, view):
        request = RequestFactory().get("/lot/1/environmental-impact")
        request.user = SimpleNamespace(institution=SimpleNamespace(name="Pangea"))
        return render_to_string(
            "partials/lot_impact_v2.html",
            {"lv": self.view(view=view), "lv_docs": "", "request": request},
        )

    def test_refurbisher_view(self):
        html = self.render("refurbisher")
        self.assertIn("What reuse bought", html)
        self.assertIn("1 of 3 devices has not left the workshop", html)

    def test_supplier_report(self):
        html = self.render("supplier")
        self.assertIn("Devices from rsc@example.org", html)
        self.assertIn("lost with the recycled devices", html)
        self.assertIn("contribution shared along the reuse chain", html)

    def test_recipient_report(self):
        html = self.render("recipient")
        self.assertIn("Embodied emissions attributed to your devices", html)
        self.assertNotIn("Verifiable certificate", html)
        self.assertIn("cannot be compared to the result of another LCA", html)

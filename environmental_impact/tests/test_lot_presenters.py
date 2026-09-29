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

    def test_inclusion_only_reaches_the_refurbisher_view(self):
        inclusion = {"people": 2, "hours": 1234}
        def view(v):
            return lot_impact_view(self.lot, self.rows, tag_name="Entrada", view=v,
                                   prepared_for="x", lot_name="L1", inclusion=inclusion)
        self.assertEqual(view("refurbisher")["inclusion"], inclusion)
        self.assertIsNone(view("supplier")["inclusion"])
        self.assertIsNone(view("recipient")["inclusion"])

    def test_carbon_cost_per_person(self):
        view = self.view()
        self.assertEqual(view["cost_per_person_reuse_text"], kg(self.lot.cost_second_users / self.lot.reused))
        self.assertEqual(view["cost_per_person_new_text"], kg(self.lot.cost_with_new / self.lot.reused))

    def test_social_wording_warns_against_impact_claims(self):
        view = self.view()
        self.assertTrue(any("gave 1 person a computer" in t for t in view["supplier_ok"]))
        self.assertTrue(any("digital divide" in t for t in view["supplier_no"]))
        self.assertTrue(any("digital divide" in t for t in view["recipient_no"]))

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
        self.assertIn("What giving these computers cost", html)
        self.assertIn("Recycling it instead would have given nobody a computer", html)
        self.assertIn("1 of 3 devices has not left the workshop", html)
        self.assertIn("2 h per desktop and 3 h per laptop refurbished, 0.7 h and 0.8 h prepared for recycling", html)
        self.assertIn('id="eil-src-3"', html)  # the tile's superscript points at its source
        self.assertIn("Nothing to do", html)  # the fixture has every reading it needs

    def test_supplier_report(self):
        html = self.render("supplier")
        self.assertIn("Devices from rsc@example.org", html)
        self.assertIn("When your devices were handed over", html)
        self.assertIn("contribution shared along the reuse chain", html)

    def test_reports_show_measured_hours_only(self):
        # the fixture's reused device has a measured second life; nothing projected is quoted
        for view in ("refurbisher", "supplier", "recipient"):
            html = self.render(view)
            self.assertNotIn("projected", html, view)
            self.assertNotIn("kWh", html, view)
            self.assertIn("5,743", html, view)

    def test_giving_compares_reuse_with_new_not_recycling(self):
        lv = self.view(view="refurbisher")
        reuse, new = lv["giving"]
        self.assertAlmostEqual(reuse["value"], self.lot.s2 - self.lot.s1)
        self.assertAlmostEqual(new["value"], self.lot.s3 - self.lot.s1)
        self.assertEqual(new["width"], 100.0)

    def test_reuse_is_cheapest_per_hour_of_use(self):
        per_hour = {s["key"]: s["g_per_hour"] for s in self.view(view="refurbisher")["scenarios"]}
        self.assertLess(per_hour["S2"], per_hour["S1"])
        self.assertLess(per_hour["S2"], per_hour["S3"])

    def test_devices_to_scan_are_listed(self):
        impacts = [impact([3696]), impact([0], reuse_start=None)]  # reused without a later scan; no reading
        rows = [(device(i), d) for i, d in enumerate(impacts)]
        lv = lot_impact_view(aggregate_lot(impacts), rows, tag_name="Salida", view="refurbisher",
                             prepared_for="x", lot_name="L2")
        self.assertEqual([r["shortid"] for r in lv["rows_awaiting_scan"]], ["ABC0"])
        self.assertEqual([r["shortid"] for r in lv["rows_missing_life1"]], ["ABC1"])

    def test_headline_below_manufacturer_range_reads_at_least(self):
        lv = self.view(view="supplier")
        self.assertTrue(lv["avoided_below_range"])  # desktop: ADEME 161 kg < Boavizta p10
        self.assertIn("at least", self.render("supplier"))
        self.assertTrue(lv["supplier_ok"][0].count("at least"))

    def test_supplier_lists_what_happened_to_each_device(self):
        html = self.render("supplier")
        self.assertIn("Your devices", html)
        self.assertIn("Used since", html)
        self.assertIn("In the workshop", html)

    def test_recipient_columns_in_plain_words(self):
        html = self.render("recipient")
        for text in ("Used before you got it", "Counts in your inventory", "If bought new"):
            self.assertIn(text, html)
        self.assertNotIn("Your share", html)

    def test_avoided_emissions_in_car_km(self):
        lv = self.view(view="supplier")
        self.assertEqual(lv["avoided_car_km"], 630)  # 161 kg / 0.256 kg per km, rounded to tens
        self.assertIn("630 km", self.render("supplier"))

    def test_awaiting_scan_is_counted(self):
        lv = self.view(view="supplier")
        self.assertEqual(lv["hours_measured"], 5743)
        self.assertEqual(lv["awaiting_scan"], 0)
        self.assertEqual(lv["scanned_again"], 1)

    def test_recipient_labels_the_per_owner_split_as_derived(self):
        html = self.render("recipient")
        self.assertIn("DeviceHub's derivation", html)
        self.assertNotIn("2nd-life share", self.render("refurbisher"))

    def render_with_inclusion(self, view):
        request = RequestFactory().get("/lot/1/environmental-impact")
        request.user = SimpleNamespace(institution=SimpleNamespace(name="Pangea"))
        lv = lot_impact_view(self.lot, self.rows, tag_name="Entrada", view=view, prepared_for="x",
                             lot_name="L1", inclusion={"people": 3, "hours": 4321})
        return render_to_string("partials/lot_impact_v2.html", {"lv": lv, "lv_docs": "", "request": request})

    def test_social_value_in_every_view_inclusion_only_internal(self):
        for view in ("refurbisher", "supplier", "recipient"):
            html = self.render_with_inclusion(view)
            self.assertIn("Social value", html, view)
            self.assertEqual("4,321" in html or "4321" in html, view == "refurbisher", view)

    def test_recipient_report(self):
        html = self.render("recipient")
        self.assertIn("Embodied emissions attributed to your devices", html)
        self.assertNotIn("Verifiable certificate", html)
        self.assertIn("cannot be compared to the result of another LCA", html)

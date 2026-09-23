"""Unit tests for the social-impact (digital inclusion) calculation.

These exercise the pure helpers in isolation (no DB, no Xapian) by feeding a
synthetic evidence timeline, plus an integration-style test of
``compute_device_social_impact`` with its collaborators patched. The headline
case is a device that goes through several lifecycles:

    refurbish -> inclusion -> sold back -> donated -> inclusion again

i.e. two disjoint inclusion periods, which must credit only the flagged spans
and skip the customer-use gap in between.
"""

import unittest
from unittest.mock import Mock, patch

from device.models import Device
from environmental_impact.social_impact import (
    compute_device_social_impact,
    evidence_timeline,
    expand_intervals_to_flagged_uuids,
    inclusion_hours_from_flags,
    _flagged_intervals_for_display,
)


def make_timeline(*pairs):
    """Build a timeline from (uuid, poh) pairs, oldest first."""
    return [
        {"uuid": u, "date": "2025-%02d-01" % (i + 1), "poh": poh}
        for i, (u, poh) in enumerate(pairs)
    ]


# Lifecycle: refurbish(A) -> inclusion A..C -> sold(D) -> donated(E) -> inclusion E..F
LIFECYCLE = make_timeline(
    ("A", 100),   # refurbish done
    ("B", 400),   # inclusion period 1
    ("C", 900),   # sold back to customer (period 1 ends)
    ("D", 1000),  # customer use (NOT inclusion)
    ("E", 1100),  # donated back
    ("F", 2000),  # inclusion period 2
)


class ExpandIntervalsTests(unittest.TestCase):

    def test_single_interval_flags_inner_spans(self):
        flagged = expand_intervals_to_flagged_uuids(LIFECYCLE, [("A", "C")])
        # spans A->B and B->C => evidences A and B flagged, not C.
        self.assertEqual(flagged, {"A", "B"})

    def test_open_ended_interval_runs_to_latest(self):
        flagged = expand_intervals_to_flagged_uuids(LIFECYCLE, [("E", "")])
        # E is index 4, latest is F => only span E->F => {E}.
        self.assertEqual(flagged, {"E"})

    def test_multiple_disjoint_intervals_union(self):
        flagged = expand_intervals_to_flagged_uuids(
            LIFECYCLE, [("A", "C"), ("E", "F")]
        )
        self.assertEqual(flagged, {"A", "B", "E"})

    def test_overlapping_intervals_do_not_duplicate(self):
        flagged = expand_intervals_to_flagged_uuids(
            LIFECYCLE, [("A", "C"), ("B", "D")]
        )
        # union of spans {A,B} and {B,C} => {A,B,C}.
        self.assertEqual(flagged, {"A", "B", "C"})

    def test_unknown_from_is_ignored(self):
        flagged = expand_intervals_to_flagged_uuids(LIFECYCLE, [("ZZZ", "C")])
        self.assertEqual(flagged, set())


class InclusionHoursTests(unittest.TestCase):

    def test_sums_only_flagged_spans(self):
        hours = inclusion_hours_from_flags(LIFECYCLE, {"A", "B", "E"})
        # A->B 300, B->C 500, E->F 900 = 1700; skips the customer gap C..E.
        self.assertEqual(hours, 1700)

    def test_no_flags_is_zero(self):
        self.assertEqual(inclusion_hours_from_flags(LIFECYCLE, set()), 0)

    def test_negative_delta_is_clamped(self):
        # A disk swap could reset PoH; a flagged span must never go negative.
        tl = make_timeline(("A", 500), ("B", 100))
        self.assertEqual(inclusion_hours_from_flags(tl, {"A"}), 0)


class FlaggedIntervalsForDisplayTests(unittest.TestCase):

    def test_collapses_into_contiguous_runs(self):
        intervals = _flagged_intervals_for_display(LIFECYCLE, {"A", "B", "E"})
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0]["from_uuid"], "A")
        self.assertEqual(intervals[0]["to_uuid"], "C")
        self.assertEqual(intervals[1]["from_uuid"], "E")
        self.assertEqual(intervals[1]["to_uuid"], "F")


class ComputeDeviceSocialImpactTests(unittest.TestCase):

    def setUp(self):
        self.device = Mock(spec=Device)
        self.device.uuids = [p["uuid"] for p in LIFECYCLE]
        self.institution = Mock()

    def _compute(self, vulnerable, flagged, usage_hours=1900):
        with patch(
            "environmental_impact.social_impact.evidence_timeline",
            return_value=LIFECYCLE,
        ), patch(
            "environmental_impact.social_impact.read_vulnerable_flag",
            return_value=vulnerable,
        ), patch(
            "environmental_impact.social_impact.read_flagged_uuids",
            return_value=set(flagged),
        ), patch(
            "environmental_impact.social_impact.get_poh_from_device",
            return_value=usage_hours,
        ):
            return compute_device_social_impact(self.device, self.institution)

    def test_not_vulnerable_credits_zero_hours(self):
        impact = self._compute(vulnerable=False, flagged={"A", "B"})
        self.assertEqual(impact.digital_inclusion_hours, 0)

    def test_vulnerable_without_flags_credits_whole_usage(self):
        impact = self._compute(vulnerable=True, flagged=set(), usage_hours=1900)
        self.assertEqual(impact.digital_inclusion_hours, 1900)
        self.assertEqual(impact.relevant_input_data["inclusion_periods"], 0)

    def test_two_disjoint_inclusion_periods(self):
        impact = self._compute(vulnerable=True, flagged={"A", "B", "E"})
        self.assertEqual(impact.digital_inclusion_hours, 1700)
        self.assertEqual(impact.relevant_input_data["inclusion_periods"], 2)


class EvidenceTimelineTests(unittest.TestCase):

    def test_builds_sorted_timeline_with_poh(self):
        device = Mock(spec=Device)
        device.uuids = ["u2", "u1"]

        evidences = {
            "u1": Mock(created="2025-01-01"),
            "u2": Mock(created="2025-05-01"),
        }

        def fake_evidence(uuid):
            ev = evidences[uuid]
            ev.get_doc = Mock()
            ev.get_time = Mock()
            return ev

        def fake_poh(ev):
            return 100 if ev is evidences["u1"] else 700

        with patch(
            "environmental_impact.social_impact.Evidence", side_effect=fake_evidence
        ), patch(
            "environmental_impact.social_impact.get_poh_from_evidence",
            side_effect=fake_poh,
        ):
            timeline = evidence_timeline(device)

        # Sorted oldest-first regardless of uuids order.
        self.assertEqual([t["uuid"] for t in timeline], ["u1", "u2"])
        self.assertEqual([t["poh"] for t in timeline], [100, 700])


if __name__ == "__main__":
    unittest.main()

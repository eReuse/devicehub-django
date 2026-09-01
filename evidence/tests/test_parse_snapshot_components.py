from django.test import TestCase

from evidence.parse_details import ParseSnapshot
from evidence.old_parse_details import ParseSnapshot as OldParseSnapshot


class SnapshotWithoutComponentsTests(TestCase):
    """Old snapshots may carry an explicit "components": null, which a
    default of [] does not catch."""

    def snapshot(self, components):
        return {
            "software": "Workbench",
            "uuid": "8f5d3b6e-0b7d-4f5a-9c3e-1a2b3c4d5e6f",
            "device": {"type": "Laptop"},
            "components": components,
        }

    def test_old_parser_turns_null_components_into_a_list(self):
        parsed = OldParseSnapshot(self.snapshot(None))
        self.assertEqual(parsed.components, [])

    def test_dispatcher_turns_null_components_into_a_list(self):
        parsed = ParseSnapshot(self.snapshot(None))
        self.assertEqual(parsed.components, [])

    def test_missing_components_key_is_also_a_list(self):
        snapshot = self.snapshot(None)
        del snapshot["components"]
        self.assertEqual(ParseSnapshot(snapshot).components, [])

    def test_components_are_read_from_the_parser(self):
        # the dispatcher must expose what the parser built, not the raw json
        parsed = ParseSnapshot(
            self.snapshot([{"type": "Processor", "actions": ["erase"]}])
        )
        self.assertEqual(parsed.components, [{"type": "Processor"}])

import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase

from dhemail.models import InstitutionTemplate, LotTemplate
from dhemail.views import _render_fresh
from lot.models import Lot, LotTag
from user.models import Institution, User


def _make_file_patcher(content):
    """Write content to a temp file and return (path, patcher) for loader.get_template."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    mock_tmpl = MagicMock()
    mock_tmpl.origin.name = tmp.name
    return tmp.name, patch("dhemail.views.loader.get_template", return_value=mock_tmpl)


class RenderFreshHierarchyTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution")
        self.tag = LotTag.objects.create(name="Tag", owner=self.institution)
        self.lot = Lot.objects.create(
            name="Test Lot", owner=self.institution, type=self.tag
        )
        self.template_name = "donor/subject.txt"

    def test_falls_back_to_file_when_no_db_entry(self):
        path, patcher = _make_file_patcher("file content")
        try:
            with patcher:
                result = _render_fresh(self.template_name, {})
            self.assertIn("file content", result)
        finally:
            os.unlink(path)

    def test_institution_overrides_file(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=self.template_name,
            content="institution content\n",
        )
        path, patcher = _make_file_patcher("file content")
        try:
            with patcher:
                result = _render_fresh(self.template_name, {}, institution=self.institution)
            self.assertIn("institution content", result)
            self.assertNotIn("file content", result)
        finally:
            os.unlink(path)

    def test_lot_overrides_institution(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=self.template_name,
            content="institution content\n",
        )
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=self.template_name,
            content="lot content\n",
        )
        path, patcher = _make_file_patcher("file content")
        try:
            with patcher:
                result = _render_fresh(
                    self.template_name, {}, institution=self.institution, lot=self.lot
                )
            self.assertIn("lot content", result)
            self.assertNotIn("institution content", result)
            self.assertNotIn("file content", result)
        finally:
            os.unlink(path)

    def test_lot_overrides_file_without_institution_entry(self):
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=self.template_name,
            content="lot content\n",
        )
        path, patcher = _make_file_patcher("file content")
        try:
            with patcher:
                result = _render_fresh(
                    self.template_name, {}, institution=self.institution, lot=self.lot
                )
            self.assertIn("lot content", result)
            self.assertNotIn("file content", result)
        finally:
            os.unlink(path)

    def test_no_lot_uses_institution(self):
        InstitutionTemplate.objects.create(
            institution=self.institution,
            template_name=self.template_name,
            content="institution content\n",
        )
        path, patcher = _make_file_patcher("file content")
        try:
            with patcher:
                result = _render_fresh(
                    self.template_name, {}, institution=self.institution, lot=None
                )
            self.assertIn("institution content", result)
            self.assertNotIn("file content", result)
        finally:
            os.unlink(path)

    def test_template_variables_are_rendered(self):
        LotTemplate.objects.create(
            lot=self.lot,
            template_name=self.template_name,
            content="Hello {{ name }}\n",
        )
        result = _render_fresh(
            self.template_name, {"name": "World"}, lot=self.lot
        )
        self.assertIn("Hello World", result)

    def test_different_lots_have_independent_templates(self):
        lot2 = Lot.objects.create(
            name="Lot 2", owner=self.institution, type=self.tag
        )
        LotTemplate.objects.create(
            lot=self.lot, template_name=self.template_name, content="lot1 content\n"
        )
        LotTemplate.objects.create(
            lot=lot2, template_name=self.template_name, content="lot2 content\n"
        )
        result1 = _render_fresh(self.template_name, {}, lot=self.lot)
        result2 = _render_fresh(self.template_name, {}, lot=lot2)
        self.assertIn("lot1 content", result1)
        self.assertIn("lot2 content", result2)

import copy
import json
import unittest
from pathlib import Path

from bible_reader.render import escape_latex, render_document

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "demo.reader.json"


class ReaderRenderingTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_unicode_order_and_marks_are_preserved(self):
        # Deliberately noncanonical combining-mark order: do not normalize it.
        surface = "ש\u05c1\u05b8\u0591"
        self.document["verses"][0]["tokens"][0]["surface"] = surface
        rendered = render_document(self.document)
        self.assertIn(surface, rendered)
        self.assertLess(rendered.index(surface), rendered.index("בֵּן"))

    def test_tex_metacharacters_are_escaped_once(self):
        self.assertEqual(
            escape_latex("\\{}$&#%_~^"),
            r"\textbackslash{}\{\}\$\&\#\%\_\textasciitilde{}\textasciicircum{}",
        )
        self.document["entries"][0]["gloss"] = r"\input{private} & 50%"
        self.document["title"] = "$notes"
        rendered = render_document(self.document)
        self.assertNotIn(r"\input{private}", rendered)
        self.assertIn(r"\textbackslash{}input\{private\} \& 50\%", rendered)
        self.assertIn(r"\$notes", rendered)

    def test_occurrence_numbering_and_explicit_omission(self):
        rendered = render_document(self.document)
        for number in range(1, 4):
            self.assertEqual(rendered.count(rf"\textsuperscript{{\textenglish{{{number}}}}}"), 1)
            self.assertEqual(rendered.count(rf"\noindent\textsuperscript{{{number}}}"), 1)
        self.assertNotIn(r"\textsuperscript{\textenglish{4}}", rendered)
        self.assertEqual(rendered.count("Synthetic help A"), 2)

    def test_render_is_deterministic_and_does_not_mutate_input(self):
        original = copy.deepcopy(self.document)
        self.assertEqual(render_document(self.document), render_document(self.document))
        self.assertEqual(self.document, original)

    def test_dangling_lexical_reference_is_rejected(self):
        self.document["verses"][0]["tokens"][0]["entry_id"] = "missing:123"
        with self.assertRaisesRegex(ValueError, "unknown entry ID"):
            render_document(self.document)

    def test_duplicate_ids_and_references_are_rejected(self):
        for kind in ("entry", "token", "verse"):
            with self.subTest(kind=kind):
                doc = copy.deepcopy(self.document)
                if kind == "entry":
                    doc["entries"].append(doc["entries"][0])
                elif kind == "token":
                    doc["verses"][1]["tokens"][0]["id"] = doc["verses"][0]["tokens"][0]["id"]
                else:
                    doc["verses"][1]["reference"] = doc["verses"][0]["reference"]
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    render_document(doc)

    def test_incompatible_language_version_and_structure_are_rejected(self):
        for field, value in [
            ("language", "grc"),
            ("schema_version", True),
            ("verses", []),
            ("title", "bad\x00text"),
            ("entries", {}),
        ]:
            with self.subTest(field=field):
                doc = copy.deepcopy(self.document)
                doc[field] = value
                with self.assertRaises(ValueError):
                    render_document(doc)

    def test_no_selected_notes_is_supported(self):
        self.document["entries"] = []
        for verse in self.document["verses"]:
            for token in verse["tokens"]:
                token["entry_id"] = None
        self.assertIn("No lexical helps selected.", render_document(self.document))


if __name__ == "__main__":
    unittest.main()

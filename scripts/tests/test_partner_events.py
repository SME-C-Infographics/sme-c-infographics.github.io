"""Standard-library tests for the Markdown partner event publishing path."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "generate-partner-events.py"
SPEC = importlib.util.spec_from_file_location("partner_events", SCRIPT)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class PartnerEventTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.fields = {
            "title": "Build an Azure solution",
            "partner": "Contoso",
            "start": "2026-12-10T10:00-06:00",
            "end": "2026-12-10T11:00-06:00",
            "format": "Virtual",
            "location": "Online",
            "registration_url": "https://example.com/register?event=1&source=partner",
            "cost": "Free",
            "topics": "Azure, AI",
        }

    def write_event(self, name="2026-12-10-contoso.md", fields=None, body="A workshop for customers."):
        fields = self.fields if fields is None else fields
        path = self.root / name
        metadata = "\n".join(f"{key}: {json.dumps(value)}" for key, value in fields.items())
        path.write_text(f"---\n{metadata}\n---\n\n{body}\n", encoding="utf-8")
        return path

    def test_parses_template_when_copied_to_event_filename(self):
        template = generator.SOURCE / "_template.md"
        path = self.root / "sample-event.md"
        path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(generator.parse_event(path)["format"], "Virtual")

    def test_parses_offset_and_topics(self):
        event = generator.parse_event(self.write_event())
        self.assertEqual(event["topics"], ["Azure", "AI"])
        self.assertEqual(event["start_date"].astimezone(timezone.utc).hour, 16)

    def test_accepts_plain_and_single_quoted_metadata(self):
        path = self.write_event()
        content = path.read_text(encoding="utf-8")
        content = content.replace('"Contoso"', "'Contoso''s workshops'")
        content = content.replace('"Virtual"', "Virtual")
        path.write_text(content, encoding="utf-8")
        self.assertEqual(generator.parse_event(path)["partner"], "Contoso's workshops")

    def test_accepts_bom_crlf_and_utc(self):
        self.fields["start"] = "2026-12-10T16:00Z"
        self.fields["end"] = "2026-12-10T17:00Z"
        path = self.write_event()
        content = path.read_text(encoding="utf-8")
        path.write_bytes(b"\xef\xbb\xbf" + content.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(generator.parse_event(path)["start_date"].utcoffset().total_seconds(), 0)

    def test_accepts_end_across_clock_change(self):
        self.fields["start"] = "2026-11-01T01:30-05:00"
        self.fields["end"] = "2026-11-01T01:15-06:00"
        event = generator.parse_event(self.write_event())
        self.assertGreater(event["end_date"], event["start_date"])

    def test_rejects_each_missing_required_field(self):
        for field in generator.REQUIRED:
            with self.subTest(field=field):
                fields = {key: value for key, value in self.fields.items() if key != field}
                with self.assertRaisesRegex(ValueError, "missing required fields"):
                    generator.parse_event(self.write_event(fields=fields))

    def test_rejects_invalid_fields(self):
        cases = [
            ("start", "2026-12-10T10:00", "UTC offset"),
            ("start", "2026-02-30T10:00Z", "not a valid date"),
            ("start", "2026-12-10T10:00+01:99", "invalid UTC offset"),
            ("start", "2026-12-10T10:00+24:00", "invalid UTC offset"),
            ("end", "2026-12-10T10:00-06:00", "later than start"),
            ("end", "2026-12-09T10:00-06:00", "later than start"),
            ("format", "Webinar", "format must be"),
            ("registration_url", "javascript:alert(1)", "absolute HTTPS"),
            ("registration_url", "https:///register", "absolute HTTPS"),
            ("registration_url", "https://name:password@example.com", "without credentials"),
            ("registration_url", "https://example.com:bad", "valid URL"),
            ("registration_url", "https://example.com\\@other.example", "absolute HTTPS"),
            ("registration_url", "https://example.com/a b", "absolute HTTPS"),
            ("topics", "Azure,,AI", "empty or duplicate"),
            ("topics", "Azure, Azure", "empty or duplicate"),
            ("title", "", "must contain text"),
            ("partner", "Contoso\nInjected", "single line"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                fields = {**self.fields, field: value}
                with self.assertRaisesRegex(ValueError, message):
                    generator.parse_event(self.write_event(fields=fields))

    def test_rejects_malformed_frontmatter_and_empty_description(self):
        path = self.write_event()
        valid = path.read_text(encoding="utf-8")
        cases = [
            (valid.removeprefix("---\n"), "start the file"),
            (valid.replace("\n---\n", "\n", 1), "close the metadata"),
            (valid.replace("---\n", "---\nextra: value\n", 1), "unknown or malformed"),
            (valid.replace("---\n", "---\ntitle: Duplicate\n", 1), "duplicate"),
            (valid.replace('title: "Build an Azure solution"', 'title: "Unclosed'), "invalid double-quoted"),
            (valid.replace('title: "Build an Azure solution"', "title: 'Unclosed"), "unclosed single-quoted"),
        ]
        for text, message in cases:
            with self.subTest(message=message):
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    generator.parse_event(path)
        with self.assertRaisesRegex(ValueError, "add a description"):
            generator.parse_event(self.write_event(body=""))

    def test_rejects_bad_filename(self):
        for name in ("Not-Kebab.md", "spaces here.md", "event_name.md"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "kebab-case"):
                generator.parse_event(self.write_event(name=name))

    def test_load_skips_templates_and_sorts_absolute_times(self):
        (self.root / "_template.md").write_text("not an event", encoding="utf-8")
        self.write_event("later.md")
        fields = {**self.fields, "start": "2026-12-10T15:00Z"}
        self.write_event("earlier.md", fields=fields)
        events = generator.load_events(self.root)
        self.assertEqual([event["id"] for event in events], ["earlier", "later"])

    def test_load_reports_all_invalid_submissions(self):
        (self.root / "bad.md").write_text("invalid", encoding="utf-8")
        (self.root / "also-bad.md").write_text("invalid", encoding="utf-8")
        (self.root / "nested").mkdir()
        with self.assertRaises(ValueError) as error:
            generator.load_events(self.root)
        for name in ("bad.md", "also-bad.md", "nested"):
            self.assertIn(name, str(error.exception))
        with self.assertRaisesRegex(ValueError, "source directory not found"):
            generator.load_events(self.root / "missing")

    def test_renders_safe_html_and_supported_description(self):
        self.fields["title"] = 'A <script>alert("title")</script>'
        self.fields["partner"] = 'A "quoted" & <partner>'
        body = '<img src=x onerror=alert(1)>\n\n- Takeaway one\n- Takeaway two\n\nFinal paragraph.'
        output = generator.render_event(generator.parse_event(self.write_event(body=body)))
        self.assertNotIn("<script>", output)
        self.assertNotIn("<img", output)
        self.assertIn("&lt;img", output)
        self.assertIn("<ul><li>Takeaway one</li><li>Takeaway two</li></ul>", output)
        self.assertIn('rel="noopener noreferrer"', output)
        self.assertIn("&amp;source=partner", output)
        self.assertIn('id="event-2026-12-10-contoso"', output)

    def test_generation_is_idempotent_and_preserves_surrounding_chrome(self):
        event = generator.parse_event(self.write_event())
        prefix = '<head><!-- smec-meta v1 --></head>\n'
        suffix = '\n<a data-smec-back-button="v2">Back</a>'
        content = prefix + generator.START + "\nstale\n" + generator.END + suffix
        generated = generator.update_page(content, [event])
        self.assertTrue(generated.startswith(prefix))
        self.assertTrue(generated.endswith(suffix))
        self.assertNotIn("stale", generated)
        self.assertEqual(generator.update_page(generated, [event]), generated)
        removed = generator.update_page(generated, [])
        self.assertNotIn("<article", removed)

    def test_missing_duplicate_and_reversed_markers_fail(self):
        for content in ("no markers", generator.START * 2 + generator.END, generator.END + generator.START):
            with self.subTest(content=content), self.assertRaises(ValueError):
                generator.update_page(content, [])

    def run_main(self, args):
        with patch("sys.argv", [str(SCRIPT), *args]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return generator.main()

    def test_cli_validate_and_check_do_not_write(self):
        page = self.root / "page.html"
        page.write_text(generator.START + "\nstale\n" + generator.END, encoding="utf-8")
        before = page.read_bytes()
        event = generator.parse_event(self.write_event())
        with patch.object(generator, "PAGE", page), patch.object(generator, "ROOT", self.root), patch.object(generator, "load_events", return_value=[event]):
            self.assertEqual(self.run_main(["--validate-only"]), 0)
            self.assertEqual(self.run_main(["--check"]), 1)
            self.assertEqual(page.read_bytes(), before)
            self.assertEqual(self.run_main([]), 0)
            self.assertEqual(self.run_main(["--check"]), 0)
            generated = page.read_bytes()
            self.assertEqual(self.run_main([]), 0)
            self.assertEqual(page.read_bytes(), generated)

    def test_cli_validation_errors_leave_page_unchanged(self):
        page = self.root / "page.html"
        page.write_text(generator.START + "\n\n" + generator.END, encoding="utf-8")
        before = page.read_bytes()
        with patch.object(generator, "PAGE", page), patch.object(generator, "load_events", side_effect=ValueError("Invalid source")):
            self.assertEqual(self.run_main([]), 1)
            self.assertEqual(page.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

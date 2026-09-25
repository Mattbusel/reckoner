"""Tests for the reckoner command line. Pure stdlib."""
import contextlib
import csv
import io
import json
import os
import tempfile
import unittest

from reckoner import __version__
from reckoner.cli import InputError, main, parse_records


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:  # argparse --version / --help
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class TestParse(unittest.TestCase):
    def test_csv(self):
        rows = parse_records("Name,CIK\nAcme Inc,1\n", ".csv")
        self.assertEqual(rows, [{"Name": "Acme Inc", "CIK": "1"}])

    def test_json_array_and_lines(self):
        self.assertEqual(parse_records('[{"name": "A"}]'), [{"name": "A"}])
        self.assertEqual(parse_records('{"name": "A"}\n{"name": "B"}\n'),
                         [{"name": "A"}, {"name": "B"}])

    def test_csv_with_unquoted_comma_is_rejected(self):
        with self.assertRaises(InputError) as ctx:
            parse_records("Name,CIK\nBecton, Dickinson and Company,1\n", ".csv")
        self.assertIn("line 2", str(ctx.exception))

    def test_bad_json(self):
        with self.assertRaises(InputError):
            parse_records("[1, 2]")
        with self.assertRaises(InputError):
            parse_records("")


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def test_version(self):
        code, out, _ = run(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)

    def test_demo_summary(self):
        code, out, _ = run(["--demo"])
        self.assertEqual(code, 0)
        self.assertIn("7 records -> 4 entities", out)
        self.assertIn("Refused merges (1)", out)

    def test_csv_roundtrip_keeps_extra_columns(self):
        path = self.write("in.csv", "Name,CIK,Region\nGENERAL ELECTRIC CO,40545,US\n"
                                    "General Electric Company,,EU\nAcme LLC,,US\n")
        out_path = os.path.join(self.tmp.name, "out.csv")
        code, _, err = run([path, "--format", "csv", "-o", out_path])
        self.assertEqual(code, 0)
        self.assertIn("3 records -> 2 entities", err)
        with open(out_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["Region"] for r in rows], ["US", "EU", "US"])
        self.assertEqual(rows[0]["entity_id"], rows[1]["entity_id"])
        self.assertNotEqual(rows[0]["entity_id"], rows[2]["entity_id"])

    def test_json_output_and_agency_mode(self):
        path = self.write("in.jsonl", '{"agency": "DoD"}\n{"agency": "U.S. Department of Defense"}\n')
        code, out, _ = run([path, "--agency", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["entities_out"], 1)

    def test_missing_file(self):
        code, _, err = run([os.path.join(self.tmp.name, "nope.csv")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)


if __name__ == "__main__":
    unittest.main()

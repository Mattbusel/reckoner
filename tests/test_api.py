"""Tests for the public resolve/match API, the evaluation helper and the benchmark."""
import contextlib
import doctest
import importlib.util
import io
import json
import unittest
from pathlib import Path

import reckoner
from reckoner import (Cluster, MatchResult, PairwiseScores, match, normalize_org,
                      pairwise_scores, resolve)
from reckoner.cli import main

ROOT = Path(__file__).resolve().parent.parent


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class TestResolve(unittest.TestCase):
    def test_plain_names(self):
        clusters = resolve(["GENERAL ELECTRIC CO", "Boeing", "General Electric Company"])
        self.assertEqual(len(clusters), 2)
        ge, boeing = clusters
        self.assertIsInstance(ge, Cluster)
        self.assertEqual(ge.members, (0, 2))
        self.assertEqual(ge.names, ("GENERAL ELECTRIC CO", "General Electric Company"))
        self.assertEqual(ge.canonical_name, "General Electric Company")
        self.assertEqual(ge.link_confidence, 0.6)
        self.assertEqual(len(ge), 2)
        self.assertEqual(len(ge.explanations), 1)
        self.assertIn("same name after normalization ('general electric')", ge.explanations[0])
        self.assertEqual(boeing.members, (1,))
        self.assertIn("no other record", boeing.explanations[0])

    def test_every_index_in_exactly_one_cluster(self):
        names = ["A Inc", "a, inc.", "B", "", "C LLC", "c"]
        clusters = resolve(names)
        seen = sorted(i for c in clusters for i in c.members)
        self.assertEqual(seen, list(range(len(names))))

    def test_records_with_identifiers_and_mixed_input(self):
        clusters = resolve([
            "GENERAL ELECTRIC CO",
            {"Name": "GE", "CIK": "0000040545"},
            {"name": "General Electric Company", "cik": "40545"},
        ])
        self.assertEqual(len(clusters), 1)
        c = clusters[0]
        self.assertEqual(c.identifiers, {"cik": "40545"})
        self.assertEqual(c.link_confidence, 0.99)
        self.assertTrue(any("shared CIK 40545" in e for e in c.explanations))

    def test_clusters_are_hashable(self):
        names = [{"name": "GENERAL ELECTRIC CO", "cik": "40545"}, "General Electric Company",
                 "Boeing"]
        first, again = resolve(names), resolve(names)
        self.assertEqual(first, again)
        self.assertEqual([hash(c) for c in first], [hash(c) for c in again])
        self.assertEqual(len(set(first) | set(again)), 2)
        self.assertEqual({c: c.canonical_name for c in first}[again[0]],
                         "General Electric Company")

    def test_refusal_is_explained_on_both_sides(self):
        clusters = resolve([
            {"name": "Meta Platforms, Inc.", "cik": "1326801"},
            {"name": "META PLATFORMS INC", "cik": "907471"},
        ])
        self.assertEqual(len(clusters), 2)
        for c in clusters:
            self.assertEqual(len(c.explanations), 1)
            self.assertIn("conflicting CIK", c.explanations[0])

    def test_agency_mode(self):
        self.assertEqual(len(resolve(["DoD", "U.S. Department of Defense"], agency=True)), 1)
        self.assertEqual(len(resolve(["DoD", "U.S. Department of Defense"])), 2)

    def test_bad_input_type(self):
        with self.assertRaises(TypeError):
            resolve([42])

    def test_empty(self):
        self.assertEqual(resolve([]), [])


class TestMatch(unittest.TestCase):
    def test_name_match(self):
        m = match("THE SHERWIN-WILLIAMS COMPANY", "Sherwin Williams Co")
        self.assertIsInstance(m, MatchResult)
        self.assertTrue(m)
        self.assertEqual((m.matched, m.score, m.method), (True, 0.6, "name_exact_normalized"))
        self.assertEqual(m.normalized, ("sherwin williams", "sherwin williams"))

    def test_similar_names_do_not_match(self):
        m = match("Meta Platforms", "Meta Financial Group")
        self.assertFalse(m)
        self.assertEqual((m.score, m.method), (0.0, "none"))
        self.assertIn("never matches on similarity", m.reasons[0])

    def test_identifier_match_uses_best_identifier(self):
        m = match({"name": "GE", "cik": "40545", "ticker": "GE"},
                  {"name": "General Electric", "cik": "0000040545", "ticker": "ge"})
        self.assertEqual((m.matched, m.score, m.method), (True, 0.99, "id:cik"))
        self.assertTrue(any("TICKER GE" in r for r in m.reasons))
        self.assertTrue(any("the shared identifier decides" in r for r in m.reasons))

    def test_conflicting_identifier_refuses(self):
        m = match({"name": "Meta Platforms, Inc.", "cik": "1326801"},
                  {"name": "META PLATFORMS INC", "cik": "907471"})
        self.assertEqual((m.matched, m.score, m.method), (False, 0.0, "refused"))
        self.assertIn("conflicting CIK", m.reasons[0])

    def test_different_ids_and_names_reported(self):
        m = match({"name": "Acme", "ein": "12-3456789"}, {"name": "Zeta", "ein": "987654321"})
        self.assertFalse(m)
        self.assertIn("different EIN: 123456789 vs 987654321", m.reasons)

    def test_state_is_evidence_only(self):
        m = match({"name": "Acme Inc", "state": "DE"}, {"name": "ACME", "state": "de"})
        self.assertIn("same state DE", m.reasons)
        self.assertEqual(m.score, 0.6)

    def test_missing_name(self):
        m = match("", "Acme")
        self.assertFalse(m)
        self.assertIn("no name", m.reasons[0])

    def test_match_agrees_with_resolve(self):
        pairs = [("Oracle Partners, L.P.", "ORACLE PARTNERS LP"),
                 ("A.G. Edwards", "AG Edwards"), ("Acme", "Acme Holdings")]
        for a, b in pairs:
            self.assertEqual(bool(match(a, b)), len(resolve([a, b])) == 1, (a, b))


class TestDottedSuffixes(unittest.TestCase):
    def test_dotted_legal_suffixes_are_stripped(self):
        self.assertEqual(normalize_org("ORACLE PARTNERS, L.P."), "oracle partners")
        self.assertEqual(normalize_org("HCMF XXII, L.L.C."), "hcmf xxii")
        self.assertEqual(normalize_org("Acme L. L. C."), "acme")
        self.assertEqual(normalize_org("Fund V - C L.P."), normalize_org("FUND V - C LP"))

    def test_suffix_after_another_dotted_abbreviation(self):
        # Each dotted abbreviation is joined on its own, from the right, so a
        # dotted suffix after "U.S." or "A.B." is stripped like a plain one.
        for dotted, plain, want in [
                ("Acme U.S. L.P.", "Acme U.S. LP", "acme u s"),
                ("Blackstone Partners U.S. L.L.C.", "Blackstone Partners U.S. LLC",
                 "blackstone partners u s"),
                ("Fund A.B. L.P.", "Fund AB LP", "fund"),
                ("Foo L.P. L.L.C.", "Foo LP LLC", "foo"),
                ("Foo P.L.L.C.", "Foo PLLC", "foo"),
                ("Foo, L.L.C.,", "Foo LLC", "foo")]:
            self.assertEqual(normalize_org(dotted), want, dotted)
            self.assertEqual(normalize_org(plain), want, plain)

    def test_match_never_starts_inside_an_abbreviation(self):
        # "l.p. l.l.c." must not be read as "p. l.l.c." (which spells "pllc").
        self.assertEqual(normalize_org("Foo L.P. L.L.C."), "foo")
        # A run that does not spell a suffix is left alone, and so is what precedes it.
        self.assertEqual(normalize_org("Foo X.L.P."), "foo x l p")
        self.assertEqual(normalize_org("Acme U.S."), "acme u s")

    def test_initials_are_untouched(self):
        # 'ag' is a legal suffix, but here it is part of the name, not its end.
        self.assertEqual(normalize_org("A.G. Edwards"), "a g edwards")
        self.assertEqual(normalize_org("U.S. Steel"), "u s steel")
        self.assertEqual(normalize_org("JPMorgan Chase Bank, N.A."), "jpmorgan chase bank n a")


class TestPairwiseScores(unittest.TestCase):
    def test_counts(self):
        s = pairwise_scores([[0, 1, 2], [3], [4, 5]], ["a", "a", "b", "b", "c", "c"])
        self.assertIsInstance(s, PairwiseScores)
        # predicted pairs: 3 + 0 + 1 = 4; right: (0,1) and (4,5); gold pairs: a 1, b 1, c 1
        self.assertEqual((s.true_positives, s.predicted_pairs, s.gold_pairs), (2, 4, 3))
        self.assertEqual((s.false_positives, s.false_negatives), (2, 1))
        self.assertAlmostEqual(s.precision, 0.5)
        self.assertAlmostEqual(s.recall, 2 / 3)
        self.assertAlmostEqual(s.f1, 2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))

    def test_degenerate(self):
        s = pairwise_scores([[0], [1]], ["a", "b"])
        self.assertEqual((s.precision, s.recall), (1.0, 1.0))
        s = pairwise_scores([[0, 1]], ["a", "b"])
        self.assertEqual((s.precision, s.recall, s.f1), (0.0, 1.0, 0.0))

    def test_rejects_bad_partitions(self):
        with self.assertRaises(ValueError):
            pairwise_scores([[0]], ["a", "b"])
        with self.assertRaises(ValueError):
            pairwise_scores([[0, 1], [1]], ["a", "b"])
        with self.assertRaises(ValueError):
            pairwise_scores([[0, 2]], ["a", "b"])


class TestMatchCli(unittest.TestCase):
    def setUp(self):
        import os
        self._old = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"

    def tearDown(self):
        import os
        if self._old is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = self._old

    def test_match_exit_codes(self):
        code, out, _ = run(["match", "GENERAL ELECTRIC CO", "General Electric Company"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("MATCH  0.60  name_exact_normalized"))
        code, out, _ = run(["match", "Meta Platforms", "Meta Financial Group"])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("NO MATCH  0.00  none"))

    def test_match_with_ids_and_json(self):
        code, out, _ = run(["match", "--a-cik", "40545", "--b-cik", "0000040545",
                            "GE", "General Electric", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual((data["matched"], data["score"], data["method"]), (True, 0.99, "id:cik"))
        self.assertEqual(data["normalized"], ["ge", "general electric"])

    def test_match_agency(self):
        code, _, _ = run(["match", "--agency", "DoD", "U.S. Department of Defense"])
        self.assertEqual(code, 0)

    def test_options_before_match(self):
        code, out, _ = run(["--color", "never", "match", "GE Co", "GE"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("MATCH  0.60"))
        code, _, _ = run(["--agency", "match", "DoD", "U.S. Department of Defense"])
        self.assertEqual(code, 0)

    def test_file_named_match(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "match"), "w", encoding="utf-8") as f:
                f.write("name\nGENERAL ELECTRIC CO\nGeneral Electric Company\n")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                for argv in (["./match"], ["--", "match"], ["--color", "never", "--", "match"]):
                    code, out, _ = run(argv)
                    self.assertEqual(code, 0, argv)
                    self.assertIn("2 records -> 1 entities", out, argv)
            finally:
                os.chdir(cwd)

    def test_match_usage_error(self):
        code, _, err = run(["match", "only-one"])
        self.assertEqual(code, 2)
        self.assertIn("reckoner match", err)


class TestDoctests(unittest.TestCase):
    def test_module_doctests(self):
        for mod in (reckoner.api, reckoner.evaluate):
            failures, _ = doctest.testmod(mod)
            self.assertEqual(failures, 0, mod.__name__)


BENCHMARK = ROOT / "benchmarks" / "run_benchmark.py"


@unittest.skipUnless(BENCHMARK.is_file() and (ROOT / "benchmarks" / "data").is_dir(),
                     "benchmarks/ is not present (e.g. tests run from an installed copy)")
class TestBenchmark(unittest.TestCase):
    """The benchmark runs on the committed GLEIF snapshot and stays above a floor."""

    def test_benchmark_snapshot(self):
        spec = importlib.util.spec_from_file_location("run_benchmark", BENCHMARK)
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        rows = bench.load(bench.DEFAULT_DATA)
        self.assertGreater(len(rows), 1000)
        all_names = bench.evaluate(rows)
        fmt = bench.evaluate([r for r in rows if r["variant"] in ("legal", "conformed")])
        self.assertGreaterEqual(all_names["precision"], 0.95)
        self.assertGreaterEqual(fmt["recall"], 0.95)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bench.main(["--min-precision", "0.95", "--min-recall", "0.95"])
        self.assertEqual(code, 0)
        self.assertIn("formatting only", out.getvalue())


if __name__ == "__main__":
    unittest.main()

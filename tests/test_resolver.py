"""Tests for reckoner. Pure stdlib, run with:  python -m pytest  (or unittest)."""
import unittest

from reckoner import EntityResolver, normalize_org, normalize_agency


class TestNormalize(unittest.TestCase):
    def test_legal_suffixes_stripped(self):
        self.assertEqual(normalize_org("GENERAL ELECTRIC CO"), "general electric")
        self.assertEqual(normalize_org("General Electric Company"), "general electric")
        self.assertEqual(normalize_org("Acme Corp LLC"), "acme")

    def test_leading_the_and_ampersand(self):
        self.assertEqual(normalize_org("THE SHERWIN-WILLIAMS COMPANY"), "sherwin williams")
        self.assertEqual(normalize_org("Sherwin Williams Co"), "sherwin williams")
        self.assertEqual(normalize_org("Becton, Dickinson & Co"), "becton dickinson and")

    def test_distinguishing_words_kept(self):
        # normalization must NOT collapse genuinely different companies
        self.assertNotEqual(normalize_org("Meta Platforms Inc"),
                            normalize_org("Meta Financial Group Inc"))

    def test_agency_alias_and_us_prefix(self):
        self.assertEqual(normalize_agency("DoD"), "department of defense")
        self.assertEqual(normalize_agency("U.S. Department of Defense"), "department of defense")
        self.assertEqual(normalize_agency("EPA"), "environmental protection agency")


class TestResolve(unittest.TestCase):
    def test_name_only_link(self):
        recs = [
            {"name": "GENERAL ELECTRIC CO"},
            {"name": "General Electric Company"},
        ]
        r = EntityResolver().resolve(recs)
        self.assertEqual(r["entities_out"], 1)
        self.assertEqual(r["entities"][0]["link_confidence"], 0.60)

    def test_identifier_merge_is_high_confidence(self):
        recs = [
            {"name": "GENERAL ELECTRIC CO", "cik": "0000040545"},
            {"name": "GE COMPANY", "cik": "40545"},   # different name, same CIK
        ]
        r = EntityResolver().resolve(recs)
        self.assertEqual(r["entities_out"], 1)
        self.assertGreaterEqual(r["entities"][0]["link_confidence"], 0.99)

    def test_id_on_one_side_only_does_not_raise_confidence(self):
        # Only one record carries the CIK, so the merge is a name link: 0.60, not 0.99.
        recs = [
            {"name": "GENERAL ELECTRIC CO", "cik": "40545"},
            {"name": "General Electric Company"},
        ]
        r = EntityResolver().resolve(recs)
        self.assertEqual(r["entities_out"], 1)
        self.assertEqual(r["entities"][0]["link_confidence"], 0.60)
        self.assertEqual(r["entities"][0]["identifiers"], {"cik": "40545"})

    def test_conflicting_strong_id_blocks_merge(self):
        recs = [
            {"name": "Meta Inc", "cik": "1326801"},
            {"name": "Meta Inc", "cik": "907471"},   # identical name, different CIK
        ]
        r = EntityResolver().resolve(recs)
        self.assertEqual(r["entities_out"], 2)  # refused
        refusals = [m for m in r["matches"] if not m["merged"]]
        self.assertTrue(refusals and "conflicting" in refusals[0]["refusal_reason"].lower())

    def test_no_fuzzy_matching(self):
        # a real typo is "similar looking" but not exactly-normalized-equal, so it
        # never merges. (By contrast "Corp" vs "Corporation" DO merge: both are
        # legal suffixes stripped during normalization, not a similarity guess.)
        recs = [
            {"name": "Microsoft Corporation"},
            {"name": "Micrsoft Corporation"},  # typo in the distinguishing word
        ]
        r = EntityResolver().resolve(recs)
        self.assertEqual(r["entities_out"], 2)

    def test_every_merge_has_a_receipt(self):
        recs = [{"name": "Acme Co"}, {"name": "Acme Company"}]
        r = EntityResolver().resolve(recs)
        merges = [m for m in r["matches"] if m["merged"]]
        self.assertTrue(merges)
        self.assertTrue(merges[0]["evidence"])   # non-empty evidence trail


if __name__ == "__main__":
    unittest.main()

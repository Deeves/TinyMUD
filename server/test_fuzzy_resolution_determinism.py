"""
Test fuzzy resolution determinism to ensure stable, predictable ordering.

This test module addresses data integrity concerns by verifying that fuzzy resolution
produces consistent results regardless of input ordering, locale settings, or case variations.
"""

import pytest
from id_parse_utils import fuzzy_resolve, _suggest_by_first_letter


class TestFuzzyResolutionDeterminism:
    """Test cases for fuzzy resolution determinism and tie-breaking."""

    def test_ambiguous_prefix_matches_stable_ordering(self):
        """Test that ambiguous prefix matches are sorted deterministically."""
        # Test case: multiple candidates start with the same prefix
        candidates = ["apple", "application", "April", "approve", "apply"]
        
        # Test different input orderings to ensure consistent output
        orderings = [
            ["apple", "application", "April", "approve", "apply"],
            ["apply", "approve", "April", "application", "apple"],
            ["April", "apple", "approve", "apply", "application"],
        ]
        
        results = []
        for ordering in orderings:
            ok, err, val = fuzzy_resolve("app", ordering)
            results.append((ok, err, val))
        
        # All results should be identical (deterministic)
        assert len(set(str(r) for r in results)) == 1, f"Non-deterministic results: {results}"
        
        # Should fail with ambiguous error containing sorted suggestions
        ok, err, val = fuzzy_resolve("app", candidates)
        assert not ok
        assert err is not None
        assert "Ambiguous id" in err
        # Error should contain deterministically sorted suggestions
        # (April excluded as it doesn't match "app" prefix)
        assert "apple, application, apply, approve" in err

    def test_ambiguous_prefix_matches_case_insensitive_sorting(self):
        """Test that case variations are handled consistently in ambiguous matches."""
        candidates = ["Apple", "apple", "APPLE", "Application", "apply"]
        
        ok, err, val = fuzzy_resolve("app", candidates)
        assert not ok
        assert err is not None
        assert "Ambiguous id" in err
        
        # The error message should have deterministic, case-insensitive ordering
        # Expected order should be: APPLE, Apple, apple, Application, apply
        # (lexicographic by lowercase, then by original case)
        expected_sorted = ["APPLE", "Apple", "apple", "Application", "apply"]
        
        # Extract suggestions from error message
        # Format: "Ambiguous id. Did you mean: item1, item2, item3 ?"
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        
        assert suggestions == expected_sorted[:len(suggestions)]

    def test_ambiguous_substring_matches_stable_ordering(self):
        """Test that ambiguous substring matches are sorted deterministically."""
        candidates = ["butterfly", "flutter", "clutter", "mutter", "gutter"]
        
        # All contain "utter" as substring
        ok, err, val = fuzzy_resolve("utter", candidates)
        assert not ok
        assert err is not None
        assert "Ambiguous id" in err
        
        # Should be sorted alphabetically
        expected_order = ["butterfly", "clutter", "flutter", "gutter", "mutter"]
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        
        assert suggestions == expected_order

    def test_case_insensitive_exact_match_priority(self):
        """Test that exact matches (case-insensitive) take priority over ambiguous matches."""
        candidates = ["Apple", "apple", "application"]
        
        # Should match "Apple" exactly (case-insensitive)
        ok, err, val = fuzzy_resolve("apple", candidates)
        assert ok
        assert val == "apple"  # Should return the exact case match from candidates

    def test_unicode_and_special_characters_stable_sorting(self):
        """Test that unicode and special characters don't break deterministic sorting."""
        candidates = ["café", "cache", "car", "cañon", "cat"]
        
        ok, err, val = fuzzy_resolve("ca", candidates)
        assert not ok
        assert err is not None
        
        # Should handle unicode correctly in deterministic sorting
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        
        # Should be consistently sorted regardless of locale
        assert len(suggestions) == 5
        assert "cache" in suggestions
        assert "café" in suggestions

    def test_empty_and_edge_cases_deterministic(self):
        """Test edge cases maintain deterministic behavior."""
        candidates = ["zebra", "Zebra", "zebrafish", "ZEBRA", "zebu"]
        
        # Ambiguous prefix match (all start with "zeb")
        ok, err, val = fuzzy_resolve("zeb", candidates)
        assert not ok
        assert err is not None
        
        # Should handle deterministically
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        
        # Should be predictably ordered: case-insensitive first, then by original case
        expected = ["ZEBRA", "Zebra", "zebra", "zebrafish", "zebu"]
        assert suggestions == expected

    def test_suggestion_by_first_letter_stable_ordering(self):
        """Test that _suggest_by_first_letter produces stable results."""
        candidates = ["banana", "Bread", "butter", "BOOK", "ball"]
        
        # Test multiple calls with same input
        results = []
        for _ in range(5):
            result = _suggest_by_first_letter("b", candidates)
            results.append(result)
        
        # All results should be identical
        assert len(set(str(r) for r in results)) == 1
        
        # Should be sorted deterministically (case-insensitive, then by original case)
        expected = ["ball", "banana", "BOOK", "Bread", "butter"]  # Correct deterministic order
        actual = _suggest_by_first_letter("b", candidates)
        assert actual == expected

    def test_large_candidate_list_performance_and_determinism(self):
        """Test determinism with larger candidate lists."""
        # Generate a large list of candidates with potential ambiguities
        candidates = []
        for i in range(100):
            candidates.extend([f"test{i:02d}", f"Test{i:02d}", f"TEST{i:02d}"])
        
        # Should handle large lists deterministically
        ok, err, val = fuzzy_resolve("test", candidates)
        assert not ok  # Should be ambiguous
        assert err is not None
        
        # Should limit to 10 suggestions as specified
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        assert len(suggestions) == 10

    def test_numeric_sorting_determinism(self):
        """Test that numeric content is sorted deterministically."""
        candidates = ["item10", "item2", "item1", "item20", "item3"]
        
        ok, err, val = fuzzy_resolve("item", candidates)
        assert not ok
        assert err is not None
        
        # Should sort lexicographically (not numerically) but deterministically
        suggestions_part = err.split("Did you mean: ")[1].split(" ?")[0]
        suggestions = [s.strip() for s in suggestions_part.split(",")]
        
        # Lexicographic order: item1, item10, item2, item20, item3
        expected = ["item1", "item10", "item2", "item20", "item3"]
        assert suggestions == expected


def test_regression_multiple_runs_same_result():
    """Regression test: ensure multiple runs of the same query produce identical results."""
    candidates = ["alpha", "Alpha", "ALPHA", "alphabet", "alpine", "alternate"]
    
    # Run the same query multiple times
    results = []
    for _ in range(10):
        ok, err, val = fuzzy_resolve("alp", candidates)
        results.append((ok, err, val))
    
    # All results should be identical
    unique_results = set(str(r) for r in results)
    assert len(unique_results) == 1, f"Non-deterministic behavior detected: {unique_results}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
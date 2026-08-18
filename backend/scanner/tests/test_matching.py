"""Tests for the matcher.

These assert on routing — matched / review / unmatched — rather than exact
score values, so tuning the weights does not require rewriting the suite.
Each test targets an ambiguity deliberately planted in catalog.csv.
"""

from pathlib import Path

import pytest

from scanner.matching import (
    Matcher,
    load_catalog,
    normalize_author,
    normalize_title,
)

CATALOG = Path(__file__).resolve().parents[3] / "catalog.csv"


@pytest.fixture(scope="module")
def matcher():
    return Matcher(load_catalog(CATALOG))


# --- normalization ---------------------------------------------------------

def test_titles_lose_leading_articles_and_punctuation():
    assert normalize_title("The Hitchhiker's Guide to the Galaxy") == (
        "hitchhikers guide to the galaxy"
    )


def test_author_last_first_is_flipped():
    assert normalize_author("Tolkien, J. R. R.") == normalize_author("J.R.R. Tolkien")


def test_accents_are_folded():
    assert normalize_author("Gabriel García Márquez") == "gabriel garcia marquez"


# --- the straightforward case ----------------------------------------------

def test_clean_read_matches(matcher):
    result = matcher.match("The Great Gatsby", "F. Scott Fitzgerald")
    assert result.status == "matched"
    assert result.match_id == "gatsby"


def test_ocr_noise_still_matches(matcher):
    result = matcher.match("One Hundred Years of Solitud", "Gabriel Garcia Marquez")
    assert result.status == "matched"
    assert result.match_id == "hundred-years"


def test_surname_only_is_usable_evidence(matcher):
    result = matcher.match("Slaughterhouse Five", "Vonnegut")
    assert result.status == "matched"
    assert result.match_id == "slaughterhouse-five"


# --- one book, two titles (US / UK) ----------------------------------------

def test_uk_title_resolves_to_the_us_entry(matcher):
    result = matcher.match("Harry Potter and the Philosopher's Stone", "J.K. Rowling")
    assert result.status == "matched"
    assert result.match_id == "sorcerers-stone"


def test_alternate_title_on_a_different_series(matcher):
    result = matcher.match("The Golden Compass", "Philip Pullman")
    assert result.status == "matched"
    assert result.match_id == "northern-lights"


# --- two different books sharing a title -----------------------------------

def test_author_separates_two_books_with_the_same_title(matcher):
    dostoevsky = matcher.match("The Idiot", "Fyodor Dostoevsky")
    batuman = matcher.match("The Idiot", "Elif Batuman")
    assert dostoevsky.match_id == "idiot-dostoevsky"
    assert batuman.match_id == "idiot-batuman"
    assert dostoevsky.status == batuman.status == "matched"


def test_same_title_without_an_author_goes_to_review(matcher):
    result = matcher.match("The Idiot", "")
    assert result.status == "review"
    ids = {c.entry.id for c in result.candidates}
    assert {"idiot-dostoevsky", "idiot-batuman"} <= ids


def test_transliterated_author_still_resolves(matcher):
    result = matcher.match("Crime and Punishment", "Dostoyevsky")
    assert result.status == "matched"
    assert result.match_id == "crime-punishment"


# --- two editions of the same book -----------------------------------------

def test_two_editions_are_ambiguous_and_go_to_review(matcher):
    result = matcher.match("Dune", "Frank Herbert")
    assert result.status == "review"
    ids = {c.entry.id for c in result.candidates[:2]}
    assert ids == {"dune-1965", "dune-2005"}
    assert "ambiguous" in result.reason


# --- titles that are substrings of other titles ----------------------------

def test_short_title_does_not_lose_to_its_longer_superstring(matcher):
    result = matcher.match("The Road", "Cormac McCarthy")
    assert result.status == "matched"
    assert result.match_id == "the-road"


def test_longer_superstring_matches_itself(matcher):
    result = matcher.match("The Road Less Traveled", "M. Scott Peck")
    assert result.status == "matched"
    assert result.match_id == "road-less-traveled"


def test_sequel_is_not_confused_with_the_original(matcher):
    result = matcher.match("Dune Messiah", "Frank Herbert")
    assert result.status == "matched"
    assert result.match_id == "dune-messiah"


# --- omnibus vs contained volumes ------------------------------------------

def test_omnibus_title_matches_the_omnibus(matcher):
    result = matcher.match("The Lord of the Rings", "J.R.R. Tolkien")
    assert result.match_id == "lotr-omnibus"


def test_contained_volume_matches_the_volume(matcher):
    result = matcher.match("The Fellowship of the Ring", "Tolkien")
    assert result.status == "matched"
    assert result.match_id == "fellowship"


# --- failure and edge cases ------------------------------------------------

def test_unknown_book_is_unmatched_not_forced(matcher):
    result = matcher.match("Advanced Widget Fabrication", "Q. Nobody")
    assert result.status == "unmatched"
    assert result.match_id is None


def test_empty_read_is_unmatched(matcher):
    result = matcher.match("", "")
    assert result.status == "unmatched"
    assert result.candidates == []


def test_every_result_carries_a_status_and_candidates(matcher):
    for title, author in [
        ("Dune", "Frank Herbert"),
        ("The Idiot", ""),
        ("Qqqq Zzzz", ""),
    ]:
        result = matcher.match(title, author)
        assert result.status in {"matched", "review", "unmatched"}
        assert isinstance(result.as_dict()["candidates"], list)


def test_search_backs_manual_correction(matcher):
    results = matcher.search("hobbit")
    assert results
    assert results[0].entry.id.startswith("hobbit")


# --- books that are simply not in the catalog ------------------------------

def test_shared_stopwords_do_not_create_a_match(matcher):
    """Read off a real shelf: the book is not in the catalog, and "of the"
    should not be enough to pair it with The Lord of the Rings."""
    result = matcher.match("Song of the Sun God", "Shankari Chandran")
    assert result.status == "unmatched"
    assert result.match_id is None


def test_unknown_book_with_a_common_noun_is_unmatched(matcher):
    result = matcher.match("The Teahouse Fire", "Ellis Avery")
    assert result.status == "unmatched"


def test_author_only_read_does_not_force_a_title_match(matcher):
    result = matcher.match("", "Philippa Gregory")
    assert result.status == "unmatched"

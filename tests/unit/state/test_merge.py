"""Tests for the pure merge helpers."""

from zendure.state.merge import compute_changes, merge_values


def test_compute_changes_only_differences() -> None:
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 3}
    assert compute_changes(old, new) == {"b": 3}


def test_compute_changes_new_key_counts() -> None:
    assert compute_changes({"a": 1}, {"c": 5}) == {"c": 5}


def test_compute_changes_none_transition() -> None:
    assert compute_changes({"a": 1}, {"a": None}) == {"a": None}


def test_compute_changes_absent_key_not_deleted() -> None:
    # "a" absent from new -> not reported, not deleted here.
    assert compute_changes({"a": 1, "b": 2}, {"b": 2}) == {}


def test_merge_values_present_wins_absent_keeps() -> None:
    merged = merge_values({"a": 1, "b": 2}, {"b": 3})
    assert merged == {"a": 1, "b": 3}

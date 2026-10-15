"""Pure merge helpers (no stored state, no I/O).

Reports are treated as full snapshots where present values win and absent keys
keep their previous value. Only keys whose value actually changed are reported
as changed, which keeps change events free of noise and makes merging
deterministic.

Reports are not dropped by ``messageId``: over HTTP polling each response
answers one request on a serialized connection, so there is no reordering to
guard against, and the device may repeat or reset the id.
"""

from collections.abc import Mapping

from ..models import PropertyValue


def compute_changes(
    old: Mapping[str, PropertyValue],
    new: Mapping[str, PropertyValue],
) -> dict[str, PropertyValue]:
    """Return only the entries in ``new`` whose value differs from ``old``.

    A key absent from ``old`` counts as changed; a key absent from ``new`` is
    left untouched (never deleted).
    """
    return {k: v for k, v in new.items() if k not in old or old[k] != v}


def merge_values(
    old: Mapping[str, PropertyValue],
    new: Mapping[str, PropertyValue],
) -> dict[str, PropertyValue]:
    """Merge ``new`` over ``old`` (present wins, absent keeps old)."""
    merged = dict(old)
    merged.update(new)
    return merged


__all__ = ["compute_changes", "merge_values"]

"""Tests for app/diarize.py — segment helpers."""

import pytest

from app.diarize import _is_overlapping


def _seg(start, end, speaker="A"):
    return {"speaker": speaker, "start": start, "end": end}


class TestIsOverlapping:
    def test_non_overlapping_segments(self):
        segs = [_seg(0.0, 1.0), _seg(1.0, 2.0), _seg(2.0, 3.0)]
        assert not any(_is_overlapping(s, segs) for s in segs)

    def test_overlapping_pair(self):
        segs = [_seg(0.0, 2.0), _seg(1.5, 3.0)]
        assert _is_overlapping(segs[0], segs)
        assert _is_overlapping(segs[1], segs)

    def test_contained_segment_overlaps(self):
        outer = _seg(0.0, 5.0)
        inner = _seg(1.0, 2.0)
        segs = [outer, inner]
        assert _is_overlapping(outer, segs)
        assert _is_overlapping(inner, segs)

    def test_single_segment_never_overlaps_itself(self):
        segs = [_seg(0.0, 1.0)]
        assert not _is_overlapping(segs[0], segs)

    def test_touching_boundaries_do_not_overlap(self):
        # End of first == start of second: open interval — should not overlap
        segs = [_seg(0.0, 1.0), _seg(1.0, 2.0)]
        assert not any(_is_overlapping(s, segs) for s in segs)

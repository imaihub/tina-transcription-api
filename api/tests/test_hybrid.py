"""Tests for app/hybrid.py and app/lang_id.py — language classification logic."""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch


def _make_classifier(fry_prob: float):
    """Return a mock sklearn pipeline state that predicts fry_prob for Frisian."""
    scaler = MagicMock()
    scaler.transform = lambda x: x
    clf = MagicMock()
    clf.predict_proba = MagicMock(return_value=np.array([[fry_prob, 1 - fry_prob]]))
    return scaler, clf


class TestClassifyFromEmbeddings:
    def test_fry_wins_above_threshold(self):
        from app.lang_id import _state, classify_from_embeddings
        scaler, clf = _make_classifier(fry_prob=0.8)
        _state.update({"scaler": scaler, "classifier": clf, "stats": ["std"]})
        lang, prob = classify_from_embeddings(
            nld_emb=np.zeros(10), fry_emb=np.zeros(10)
        )
        assert lang == "fry"
        assert prob == pytest.approx(0.8)

    def test_nld_wins_below_threshold(self):
        from app.lang_id import _state, classify_from_embeddings
        scaler, clf = _make_classifier(fry_prob=0.3)
        _state.update({"scaler": scaler, "classifier": clf, "stats": ["std"]})
        lang, prob = classify_from_embeddings(
            nld_emb=np.zeros(10), fry_emb=np.zeros(10)
        )
        assert lang == "nld"
        assert prob == pytest.approx(0.3)

    def test_exactly_at_threshold_picks_fry(self):
        from app.lang_id import _state, classify_from_embeddings
        scaler, clf = _make_classifier(fry_prob=0.5)
        _state.update({"scaler": scaler, "classifier": clf, "stats": ["std"]})
        lang, _ = classify_from_embeddings(
            nld_emb=np.zeros(10), fry_emb=np.zeros(10)
        )
        assert lang == "fry"

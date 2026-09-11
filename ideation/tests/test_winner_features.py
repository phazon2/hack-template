"""The metric's gate: it must refuse to score until outcome-labelled data earns it the right."""

from __future__ import annotations

from ideate.config import Settings
from ideate.evaluation.winner_features import (
    FEATURES,
    GOODHART_PRONE,
    MIN_PER_SIDE,
    auc,
    auc_interval,
    enough_data,
    f_abstraction,
    f_moment_open,
    labelled_from_corpus,
    pitch_score,
    shortfall,
    split_labelled,
    validate,
    validated_features,
)

GALLERY = """
WINNERS
- AccessForm: Call. Talk. Your form is filled.
- Signet: anyone can check it with dig and openssl.

LISTED WITHOUT A WINNER LABEL
- Sensentia: turns human signals into real-time insights and adaptive actions.
"""


def test_split_labelled_keeps_the_two_sides_apart():
    winners, others = split_labelled([GALLERY])
    assert winners == ["Call. Talk. Your form is filled.", "anyone can check it with dig and openssl."]
    assert others == ["turns human signals into real-time insights and adaptive actions."]


def test_split_labelled_deduplicates_and_survives_an_unrelated_heading():
    winners, others = split_labelled([GALLERY + "\nNOTES\n- Ignored: not a labelled entry\n", GALLERY])
    assert len(winners) == 2 and len(others) == 1  # the second copy adds nothing
    assert all("Ignored" not in w for w in winners + others)


# --------------------------------------------------------------------------- features
def test_abstraction_scores_the_concrete_pitch_higher():
    """The one direction the observed gallery actually supports: filler is a negative signal."""
    assert f_abstraction("Call. Talk. Your form is filled.") == 1.0
    vague = f_abstraction("A seamless scalable platform that leverages real-time insights.")
    assert vague < 0.8


def test_moment_open_fires_on_a_situation_not_a_category():
    assert f_moment_open("Before you wire a rental deposit, drop in the listing's photo.") == 1.0
    assert f_moment_open("A platform for property managers.") == 0.0


def test_every_feature_is_finite_on_empty_and_odd_input():
    for name, fn in FEATURES.items():
        for text in ("", "   ", "!!!", "a"):
            value = fn(text)
            assert isinstance(value, float) and value == value, name


# --------------------------------------------------------------------------- statistics
def test_auc_is_chance_for_identical_distributions_and_one_for_separation():
    assert auc([1.0, 2.0], [1.0, 2.0]) == 0.5
    assert auc([3.0, 4.0], [1.0, 2.0]) == 1.0
    assert auc([], [1.0]) == 0.5  # no data is chance, never a confident answer


def test_auc_interval_narrows_as_the_sample_grows():
    small = auc_interval(0.70, 14, 10)
    large = auc_interval(0.70, 200, 200)
    assert small[0] < 0.5 < small[1]  # at our real sample size, 0.70 does not clear chance
    assert large[0] > 0.5
    assert (large[1] - large[0]) < (small[1] - small[0])


# --------------------------------------------------------------------------- the gate
def test_the_gate_is_shut_on_the_corpus_we_actually_have():
    """Guards the finding this module exists for: one event is not enough to validate anything."""
    winners, others = labelled_from_corpus(Settings())
    assert winners and others, "the bundled corpus should carry outcome-labelled pitches"
    assert not enough_data(winners, others)
    assert validated_features(validate(winners, others), winners, others) == []
    assert pitch_score("Call. Talk. Your form is filled.", []) is None
    assert "need 20 of each" in shortfall(winners, others)


def test_the_gate_opens_by_itself_once_the_data_arrives():
    """No hand-tuning: more labelled events is the only thing that turns the metric on."""
    winners = [f"Before you ship, check {n} with dig and openssl." for n in range(MIN_PER_SIDE)]
    others = ["A seamless scalable platform leveraging real-time insights." for _ in range(MIN_PER_SIDE)]
    assert enough_data(winners, others)
    usable = validated_features(validate(winners, others), winners, others)
    assert usable, "perfectly separated features should pass the gate at this sample size"
    score = pitch_score("Before you wire a deposit, check it with dig and openssl.", usable)
    assert score is not None and 0.0 <= score <= 1.0


def test_gameable_features_never_enter_the_composite_however_well_they_measure():
    """A generator optimising against length just writes padding, so length must never score."""
    winners = ["word " * 60 for _ in range(MIN_PER_SIDE)]
    others = ["word" for _ in range(MIN_PER_SIDE)]
    reports = validate(winners, others)
    length = next(r for r in reports if r.name == "length")
    assert length.auc > 0.9 and length.separates  # it measures perfectly
    assert not length.usable  # and is still barred
    assert not set(validated_features(reports, winners, others)) & GOODHART_PRONE


def test_a_feature_predictive_in_the_negative_direction_still_counts():
    """Winners scoring consistently LOWER is signal, not noise; orientation is folded in."""
    winners = ["Call. Talk. Your form is filled." for _ in range(MIN_PER_SIDE)]
    others = ["A seamless adaptive scalable platform." for _ in range(MIN_PER_SIDE)]
    abstraction = next(r for r in validate(winners, others) if r.name == "abstraction")
    assert abstraction.auc > 0.5

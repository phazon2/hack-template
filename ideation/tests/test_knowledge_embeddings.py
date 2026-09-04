"""HashingEmbedder: determinism, unit norm, feature hashing and idf serialization."""

import math

from ideate.knowledge.embeddings import Embedder, HashingEmbedder, _features, embedder_from_dict


def test_features_are_prefixed_unigrams_bigrams_and_padded_trigrams():
    feats = _features(["ab", "abc"])
    assert feats == ["u:ab", "u:abc", "b:ab_abc", "c:#ab", "c:ab#", "c:#ab", "c:abc", "c:bc#"]


def test_embed_is_deterministic_unit_norm_and_protocol_conformant():
    emb = HashingEmbedder(dim=64)
    assert isinstance(emb, Embedder)
    texts = ["public weather api with a free key", "demo lands in ninety seconds"]
    emb.fit(texts)
    v1, v2 = emb.embed(texts), HashingEmbedder(dim=64, idf=emb.to_dict()["idf"]).embed(texts)
    assert v1 == v2
    for v in v1:
        assert len(v) == 64
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)
    assert emb.embed([""]) == [[0.0] * 64]


def test_similar_texts_are_closer_than_unrelated_ones():
    emb = HashingEmbedder(dim=256)
    a, b, c = emb.embed(["weather forecast api", "weather forecast data", "hackathon pitch structure"])
    dot = lambda x, y: sum(p * q for p, q in zip(x, y))
    assert dot(a, b) > dot(a, c)


def test_fit_idf_formula_and_round_trip():
    emb = HashingEmbedder(dim=32)
    emb.fit(["alpha beta", "alpha gamma"])
    d = emb.to_dict()
    assert d["name"] == "hashing" and d["dim"] == 32
    assert math.isclose(d["idf"]["u:alpha"], math.log(3 / 3) + 1)
    assert math.isclose(d["idf"]["u:beta"], math.log(3 / 2) + 1)
    assert list(d["idf"]) == sorted(d["idf"])
    clone = embedder_from_dict(d)
    assert clone.to_dict() == d
    assert clone.embed(["alpha beta"]) == emb.embed(["alpha beta"])


def test_unknown_embedder_name_is_rejected():
    try:
        embedder_from_dict({"name": "sentence-transformer", "dim": 3})
    except ValueError as e:
        assert "sentence-transformer" in str(e)
    else:
        raise AssertionError("expected ValueError")

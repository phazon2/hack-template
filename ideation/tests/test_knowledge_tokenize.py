"""tokenize(): normalisation, stopwords and the ordered single-application suffix rules."""

from ideate.knowledge.tokenize import STOPWORDS, stem, tokenize


def test_lowercases_splits_and_drops_short_tokens():
    assert tokenize("Hello, World! A B C 42 x7") == ["hello", "world", "42", "x7"]


def test_stopwords_are_dropped_and_list_is_about_120_words():
    assert tokenize("the demo and the pitch") == ["demo", "pitch"]
    assert 100 <= len(STOPWORDS) <= 140
    assert "the" in STOPWORDS and "demo" not in STOPWORDS


def test_suffix_rules_apply_first_match_once_in_order():
    assert stem("carries") == "carry"  # ies -> y
    assert stem("classes") == "class"  # sses -> ss beats es/s
    assert stem("running") == "runn"  # ing -> ""
    assert stem("jumped") == "jump"  # ed -> ""
    assert stem("quickly") == "quick"  # ly -> ""
    assert stem("boxes") == "box"  # es -> ""
    assert stem("apis") == "api"  # s -> ""


def test_rule_needs_three_char_remainder_and_is_not_reapplied():
    assert stem("ing") == "ing"
    assert stem("bed") == "bed"
    assert stem("ties") == "tie"  # ies leaves 't', es leaves 'ti' (too short); s rule leaves 'tie'
    assert stem("flies") == "fli"  # ies would leave 'fl'; es applies instead
    assert stem("meetings") == "meeting"  # only the first matching rule is applied


def test_tokenize_is_deterministic_and_pure():
    text = "Deploy early: git-triggered deploys give a public URL and a webhook receiver."
    assert tokenize(text) == tokenize(text)
    assert tokenize("") == []

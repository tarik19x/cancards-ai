"""Tests for the hard-set merge/split/freeze (point 1j-iii) and the recall harness's
question selection. No API calls.

The last test is the freeze itself: it fails if a hard question, its labelled
chunks or its split is edited without a deliberate lock update.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.merge_hard_eval_questions import (
    GROUND_TRUTH_PATH,
    LOCK_PATH,
    _components,
    assign_splits,
    fingerprint,
    tag_existing,
    to_entry,
)


def _q(text: str, qtype: str, chunk: str, distractor: str | None = None) -> dict:
    q = {
        "question": text,
        "ground_truth": "an answer",
        "relevant_card_ids": ["a"],
        "answering_chunk_ids": [chunk],
        "question_type": qtype,
        "split": None,
    }
    if distractor:
        q["distractor_chunk_id"] = distractor
    return q


def test_assign_splits_halves_every_category():
    qs = [_q(f"exact {i}", "exact_term", f"e::{i}") for i in range(6)]
    qs += [_q(f"para {i}", "paraphrase", f"p::{i}") for i in range(4)]

    assign_splits(qs)

    for category in ("exact_term", "paraphrase"):
        sides = Counter(q["split"] for q in qs if q["question_type"] == category)
        assert sides["practice"] == sides["final"]


def test_assign_splits_keeps_twin_linked_questions_on_one_side():
    # q0's twin paragraph (d::1) is q1's answer, q1's twin (d::2) is q2's answer.
    linked = [
        _q("q0", "disambiguation", "d::0", distractor="d::1"),
        _q("q1", "disambiguation", "d::1", distractor="d::2"),
        _q("q2", "disambiguation", "d::2", distractor="x::9"),
    ]
    others = [_q(f"solo {i}", "disambiguation", f"s::{i}") for i in range(5)]

    assign_splits(linked + others)

    assert len({q["split"] for q in linked}) == 1
    assert Counter(q["split"] for q in linked + others) == {"practice": 4, "final": 4}


def test_assign_splits_is_deterministic():
    def build():
        return [_q(f"q {i}", "exact_term", f"e::{i}") for i in range(10)]

    first, second = build(), build()
    assign_splits(first)
    assign_splits(second)
    assert [q["split"] for q in first] == [q["split"] for q in second]


def test_assign_splits_refuses_an_odd_category():
    with pytest.raises(AssertionError):
        assign_splits([_q(f"q {i}", "exact_term", f"e::{i}") for i in range(3)])


def test_fingerprint_ignores_answer_wording_but_not_questions_or_splits():
    base = [{**to_entry({**_q("Q?", "exact_term", "e::0"), "split": "practice"})}]
    reworded = [{**base[0], "ground_truth": "a corrected answer"}]
    edited_question = [{**base[0], "question": "Q, rewritten?"}]
    moved = [{**base[0], "split": "final"}]

    assert fingerprint(base) == fingerprint(reworded)
    assert fingerprint(base) != fingerprint(edited_question)
    assert fingerprint(base) != fingerprint(moved)


def test_to_entry_carries_ids_only_never_source_text():
    q = {
        **_q("Q?", "disambiguation", "d::0", distractor="d::1"),
        "split": "final",
        "source_chunks": [{"id": "d::0", "text": "PDF text"}],
        "distractor_chunk_text": "PDF text",
    }
    entry = to_entry(q)
    assert "source_chunks" not in entry and "distractor_chunk_text" not in entry
    assert entry["eval_set"] == "hard" and entry["distractor_chunk_id"] == "d::1"


def test_tag_existing_marks_easy_and_pilot_and_leaves_hard_alone():
    entries = [
        {"question_type": "single_card"},
        {"question_type": "pdf_grounded"},
        {"question_type": "exact_term", "eval_set": "hard"},
    ]
    tag_existing(entries)
    assert [e["eval_set"] for e in entries] == ["easy", "pilot", "hard"]


def _load_measure_recall():
    path = Path(__file__).resolve().parents[3] / "tests" / "evals" / "measure_recall.py"
    spec = importlib.util.spec_from_file_location("measure_recall_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_questions_defaults_to_the_legacy_set_and_skips_unanswerable():
    select = _load_measure_recall().select_questions
    questions = [
        {"eval_set": "easy", "answering_chunk_ids": ["a"]},
        {"question_type": "old", "answering_chunk_ids": ["b"]},  # no eval_set: predates the field
        {"eval_set": "hard", "split": "practice", "answering_chunk_ids": ["c"]},
    ]
    chosen, skipped = select(questions, "legacy", None)
    assert [q["answering_chunk_ids"] for q in chosen] == [["a"], ["b"]] and skipped == 0


def test_select_questions_picks_one_hard_split_and_counts_unanswerable():
    select = _load_measure_recall().select_questions
    questions = [
        {"eval_set": "hard", "split": "practice", "answering_chunk_ids": ["a"]},
        {"eval_set": "hard", "split": "practice", "answering_chunk_ids": []},
        {"eval_set": "hard", "split": "final", "answering_chunk_ids": ["b"]},
        {"eval_set": "easy", "answering_chunk_ids": ["c"]},
    ]
    chosen, skipped = select(questions, "hard", "practice")
    assert [q["answering_chunk_ids"] for q in chosen] == [["a"]] and skipped == 1


def test_the_hard_set_is_frozen():
    entries = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    hard = [e for e in entries if e.get("eval_set") == "hard"]

    assert fingerprint(entries) == lock["fingerprint"], (
        "A hard question, its labelled chunks or its split changed. The set is frozen: "
        "never edit, add or drop one because of how a method scored it."
    )
    assert Counter(e["split"] for e in hard) == {"practice": 100, "final": 100}
    by_category = Counter((e["question_type"], e["split"]) for e in hard)
    for category in {e["question_type"] for e in hard}:
        assert by_category[(category, "practice")] == by_category[(category, "final")]

    chunks = [cid for e in hard for cid in e["answering_chunk_ids"]]
    assert len(chunks) == len(set(chunks)), "a paragraph backs two hard questions"
    for group in _components(hard):
        assert len({e["split"] for e in group}) == 1, "twin-linked questions straddle the split"

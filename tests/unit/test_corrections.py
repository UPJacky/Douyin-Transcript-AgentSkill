from __future__ import annotations

import json

import pytest
from douyin_transcript.corrections import (
    MAX_TERMINOLOGY_MATCH_STEPS,
    MAX_TERMINOLOGY_RULES,
    MAX_TERMINOLOGY_TRIE_NODES,
    CorrectionRule,
    CorrectionWorkBudget,
    apply_terminology_dictionary,
)
from douyin_transcript.limits import ResourceLimitError


def test_dictionary_is_off_by_default_and_archive_does_not_contain_transcript():
    original = "本视频的插屏表现很好"
    rules = [CorrectionRule("approved-01", "插屏", "插屏广告", "明确的商品术语")]

    result = apply_terminology_dictionary(original, rules)

    assert result.text == original
    assert result.enabled is False
    assert result.applied == ()
    record = result.archive_record()
    assert record["enabled"] is False
    assert record["rule_count"] == 1
    assert original not in json.dumps(record, ensure_ascii=False)


def test_enabled_dictionary_replaces_only_case_sensitive_literal_terms():
    rules = [CorrectionRule("acos", "ACoS", "ACoS 指标", "白名单术语")]

    result = apply_terminology_dictionary(
        "ACoS 与 acos；myACoSx 不应被改写。", rules, enabled=True
    )

    assert result.text == "ACoS 指标 与 acos；myACoSx 不应被改写。"
    assert len(result.applied) == 1
    assert result.applied[0].rule_id == "acos"
    assert result.applied[0].occurrences == 1


def test_literal_metacharacters_are_not_treated_as_patterns():
    rules = [CorrectionRule("plus", "A+B", "A plus B")]

    result = apply_terminology_dictionary("A+B AAB", rules, enabled=True)

    assert result.text == "A plus B AAB"
    assert result.applied[0].occurrences == 1


def test_longest_overlapping_source_wins_and_replacements_do_not_cascade():
    rules = [
        CorrectionRule("short", "FBA", "短规则"),
        CorrectionRule("long", "FBA 配送", "长规则"),
        CorrectionRule("chain", "短规则", "级联结果"),
    ]

    result = apply_terminology_dictionary("FBA 配送和FBA", rules, enabled=True)

    assert result.text == "长规则和短规则"
    assert [(rule.rule_id, rule.occurrences) for rule in result.applied] == [
        ("long", 1),
        ("short", 1),
    ]


def test_longest_match_falls_back_to_valid_shorter_rule_and_keeps_ascii_boundaries():
    rules = [
        CorrectionRule("short", "foo", "S"),
        CorrectionRule("long", "foo-bar", "L"),
        CorrectionRule("acos", "ACoS", "TERM"),
    ]

    result = apply_terminology_dictionary(
        "foo-barX|foo-bar!|xfoo-bar|myACoSx|ACoS!", rules, enabled=True
    )

    assert result.text == "S-barX|L!|xfoo-bar|myACoSx|TERM!"


def test_large_dictionary_workload_uses_one_trie_step_per_nonmatching_character():
    rules = tuple(
        CorrectionRule(f"r{index}", chr(0x400 + index) + "term", "replacement")
        for index in range(1_000)
    )
    text = "z" * 200_000
    budget = CorrectionWorkBudget()

    result = apply_terminology_dictionary(
        text, rules, enabled=True, work_budget=budget
    )

    assert result.text == text
    assert result.applied == ()
    assert budget.remaining_steps == MAX_TERMINOLOGY_MATCH_STEPS - len(text)


def test_shared_prefix_workload_fails_at_deterministic_match_budget():
    rules = tuple(
        CorrectionRule(f"r{length}", "a" * length + "b", "replacement")
        for length in range(1, 101)
    )
    budget = CorrectionWorkBudget(max_steps=5_000)

    with pytest.raises(ResourceLimitError, match="匹配工作量") as error:
        apply_terminology_dictionary(
            "a" * 1_000 + "c", rules, enabled=True, work_budget=budget
        )

    assert error.value.code == "TERMINOLOGY_WORK_LIMIT"
    assert budget.remaining_steps == 0


def test_dictionary_rule_count_and_trie_node_limits_fail_closed():
    too_many_rules = (
        CorrectionRule(f"r{index}", chr(0x1000 + index), chr(0x5000 + index))
        for index in range(MAX_TERMINOLOGY_RULES + 1)
    )
    with pytest.raises(ResourceLimitError) as rule_error:
        apply_terminology_dictionary("", too_many_rules)

    too_many_nodes = [
        CorrectionRule("long", "a" * MAX_TERMINOLOGY_TRIE_NODES, "b")
    ]
    with pytest.raises(ResourceLimitError) as trie_error:
        apply_terminology_dictionary("a", too_many_nodes, enabled=True)

    assert rule_error.value.code == "TERMINOLOGY_DICTIONARY_LIMIT"
    assert trie_error.value.code == "TERMINOLOGY_DICTIONARY_LIMIT"


def test_two_text_fields_can_share_one_total_match_budget():
    budget = CorrectionWorkBudget(max_steps=4)
    rule = [CorrectionRule("term", "term", "TERM")]

    first = apply_terminology_dictionary(
        "x", rule, enabled=True, work_budget=budget
    )
    second = apply_terminology_dictionary(
        "y", rule, enabled=True, work_budget=budget
    )

    assert first.text == "x"
    assert second.text == "y"
    assert budget.remaining_steps == 2


def test_archive_record_is_stable_and_changes_with_dictionary():
    first = CorrectionRule("r1", "插屏", "插屏广告", "人工审核")
    second = CorrectionRule("r2", "FBA", "FBA 物流", "")

    a = apply_terminology_dictionary("插屏和FBA", [first, second], enabled=True)
    b = apply_terminology_dictionary("插屏和FBA", [second, first], enabled=True)
    c = apply_terminology_dictionary("插屏和FBA", [first], enabled=True)

    assert a.archive_record() == b.archive_record()
    assert a.ruleset_sha256 == b.ruleset_sha256
    assert a.ruleset_sha256 != c.ruleset_sha256
    assert a.archive_record()["applied_rules"] == [
        {
            "rule_id": "r1",
            "source": "插屏",
            "replacement": "插屏广告",
            "occurrences": 1,
            "note": "人工审核",
        },
        {
            "rule_id": "r2",
            "source": "FBA",
            "replacement": "FBA 物流",
            "occurrences": 1,
            "note": "",
        },
    ]


@pytest.mark.parametrize(
    ("rule_fields", "message"),
    [
        (("r1", "x", "x"), "must differ"),
        (("r1", " ", "target"), "nonempty"),
        (("r1", "x", "y\x00"), "NUL"),
    ],
)
def test_invalid_rule_is_rejected(rule_fields: tuple[str, str, str], message: str):
    with pytest.raises(ValueError, match=message):
        apply_terminology_dictionary("text", [CorrectionRule(*rule_fields)], enabled=True)


def test_duplicate_rule_ids_and_sources_are_rejected():
    with pytest.raises(ValueError, match="duplicate correction rule id"):
        apply_terminology_dictionary(
            "x", [CorrectionRule("same", "x", "y"), CorrectionRule("same", "z", "w")]
        )
    with pytest.raises(ValueError, match="duplicate correction source"):
        apply_terminology_dictionary(
            "x", [CorrectionRule("first", "x", "y"), CorrectionRule("second", "x", "z")]
        )


def test_non_rule_values_and_non_string_text_are_rejected():
    with pytest.raises(TypeError, match="text must be a string"):
        apply_terminology_dictionary(123, [])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CorrectionRule"):
        apply_terminology_dictionary("x", [object()])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="enabled must be a bool"):
        apply_terminology_dictionary("x", [], enabled="yes")  # type: ignore[arg-type]


def test_expansion_is_rejected_before_output_is_built_past_character_budget():
    rule = CorrectionRule("expand", "x", "Y" * 10_000)

    with pytest.raises(ResourceLimitError, match="字符数上限") as error:
        apply_terminology_dictionary(
            "x!" * 50, [rule], enabled=True, max_output_characters=100
        )

    assert error.value.code == "TERMINOLOGY_OUTPUT_LIMIT"


def test_corrected_output_at_character_budget_is_allowed():
    result = apply_terminology_dictionary(
        "x!", [CorrectionRule("replace", "x", "123")],
        enabled=True,
        max_output_characters=4,
    )

    assert result.text == "123!"

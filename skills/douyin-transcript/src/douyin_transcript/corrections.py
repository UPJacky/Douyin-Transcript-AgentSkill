"""Opt-in, literal terminology corrections for ASR transcripts.

This module intentionally does not infer corrections.  Callers must provide an
explicit whitelist and pass ``enabled=True`` before any text is changed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from .limits import DEFAULT_MAX_OUTPUT_CHARACTERS, ResourceLimitError

MAX_TERMINOLOGY_RULES = 1_000
MAX_TERMINOLOGY_DICTIONARY_BYTES = 256 * 1024
MAX_TERMINOLOGY_TRIE_NODES = 65_536
MAX_TERMINOLOGY_MATCH_STEPS = 25_000_000


class _TrieNode:
    __slots__ = ("children", "rule")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.rule: CorrectionRule | None = None


class CorrectionWorkBudget:
    """A reusable hard budget for trie transitions across related text fields."""

    __slots__ = ("_remaining_steps",)

    def __init__(self, max_steps: int = MAX_TERMINOLOGY_MATCH_STEPS) -> None:
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or not 0 < max_steps <= MAX_TERMINOLOGY_MATCH_STEPS
        ):
            raise ValueError(f"max_steps must be between 1 and {MAX_TERMINOLOGY_MATCH_STEPS}")
        self._remaining_steps = max_steps

    @property
    def remaining_steps(self) -> int:
        return self._remaining_steps

    def consume(self) -> None:
        if self._remaining_steps <= 0:
            raise ResourceLimitError(
                "TERMINOLOGY_WORK_LIMIT",
                "术语匹配工作量超过安全上限；请精简词典或关闭术语纠错后重试。",
            )
        self._remaining_steps -= 1


@dataclass(frozen=True)
class CorrectionRule:
    """A single case-sensitive literal mapping approved by the caller."""

    rule_id: str
    source: str
    replacement: str
    note: str = ""

    def __post_init__(self) -> None:
        for field_name in ("rule_id", "source", "replacement"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a nonempty string")
            if "\x00" in value:
                raise ValueError(f"{field_name} must not contain NUL")
        if self.source == self.replacement:
            raise ValueError("source and replacement must differ")
        if "\n" in self.source or "\r" in self.source:
            raise ValueError("source must be a single-line literal term")
        if "\n" in self.replacement or "\r" in self.replacement:
            raise ValueError("replacement must be a single-line literal term")
        if not isinstance(self.note, str) or "\x00" in self.note:
            raise ValueError("note must be a string without NUL")


@dataclass(frozen=True)
class AppliedCorrection:
    """Internal metadata for one matched rule and its replacement count."""

    rule_id: str
    source: str
    replacement: str
    occurrences: int
    note: str


@dataclass(frozen=True)
class CorrectionResult:
    """Corrected text plus metadata; archive records never include the transcript."""

    text: str
    enabled: bool
    ruleset_sha256: str
    rule_count: int
    applied: tuple[AppliedCorrection, ...]

    def archive_record(self) -> dict[str, object]:
        """Return minimal comparison metadata without transcript or rule values."""
        return {
            "schema_version": 2,
            "ruleset_sha256": self.ruleset_sha256,
            "applied_rule_count": len(self.applied),
            "replacement_count": sum(item.occurrences for item in self.applied),
        }


def apply_terminology_dictionary(
    text: str,
    rules: Iterable[CorrectionRule],
    *,
    enabled: bool = False,
    max_output_characters: int = DEFAULT_MAX_OUTPUT_CHARACTERS,
    work_budget: CorrectionWorkBudget | None = None,
) -> CorrectionResult:
    """Apply only supplied, case-sensitive literal rules when explicitly enabled.

    Matching is performed against the original input, so replacements cannot
    cascade into another rule.  Longer overlapping sources take precedence.
    ASCII word characters adjacent to an ASCII term prevent partial-word
    matches (for example, ``ACoS`` will not match ``myACoSx``).
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a bool")
    if (
        isinstance(max_output_characters, bool)
        or not isinstance(max_output_characters, int)
        or max_output_characters <= 0
    ):
        raise ValueError("max_output_characters must be a positive integer")
    if work_budget is not None and not isinstance(work_budget, CorrectionWorkBudget):
        raise TypeError("work_budget must be a CorrectionWorkBudget or None")

    normalized_rules = _collect_rules(rules)
    _validate_rules(normalized_rules)
    fingerprint = _ruleset_fingerprint(normalized_rules)
    if not enabled or not normalized_rules or not text:
        return CorrectionResult(
            text=text,
            enabled=enabled,
            ruleset_sha256=fingerprint,
            rule_count=len(normalized_rules),
            applied=(),
        )

    if len(text) > max_output_characters:
        raise ResourceLimitError(
            "TERMINOLOGY_OUTPUT_LIMIT",
            "术语纠错结果超过设置的字符数上限；请缩短术语替换内容或调整上限。",
        )
    budget = work_budget if work_budget is not None else CorrectionWorkBudget()
    trie = _build_match_trie(normalized_rules)
    counts = {rule.rule_id: 0 for rule in normalized_rules}
    output: list[str] = []
    output_characters = 0
    cursor = 0
    while cursor < len(text):
        matched: CorrectionRule | None = None
        node = trie
        probe = cursor
        while probe < len(text):
            budget.consume()
            node = node.children.get(text[probe])
            if node is None:
                break
            probe += 1
            if node.rule is not None and _has_safe_boundaries(text, cursor, node.rule.source):
                # Trie depth increases with each source character, so the last
                # valid terminal is the longest valid match at this position.
                matched = node.rule
        if matched is None:
            if output_characters >= max_output_characters:
                raise ResourceLimitError(
                    "TERMINOLOGY_OUTPUT_LIMIT",
                    "术语纠错结果超过设置的字符数上限；请缩短术语替换内容或调整上限。",
                )
            output.append(text[cursor])
            output_characters += 1
            cursor += 1
            continue
        if output_characters + len(matched.replacement) > max_output_characters:
            raise ResourceLimitError(
                "TERMINOLOGY_OUTPUT_LIMIT",
                "术语纠错结果超过设置的字符数上限；请缩短术语替换内容或调整上限。",
            )
        output.append(matched.replacement)
        output_characters += len(matched.replacement)
        counts[matched.rule_id] += 1
        cursor += len(matched.source)

    applied = tuple(
        AppliedCorrection(
            rule_id=rule.rule_id,
            source=rule.source,
            replacement=rule.replacement,
            occurrences=counts[rule.rule_id],
            note=rule.note,
        )
        for rule in sorted(normalized_rules, key=lambda item: item.rule_id)
        if counts[rule.rule_id]
    )
    return CorrectionResult(
        text="".join(output),
        enabled=True,
        ruleset_sha256=fingerprint,
        rule_count=len(normalized_rules),
        applied=applied,
    )


def _collect_rules(rules: Iterable[CorrectionRule]) -> tuple[CorrectionRule, ...]:
    """Bound rule enumeration and fingerprint/trie input before materializing it."""
    collected: list[CorrectionRule] = []
    character_count = 0
    byte_count = 0
    for rule in rules:
        if len(collected) >= MAX_TERMINOLOGY_RULES:
            raise ResourceLimitError(
                "TERMINOLOGY_DICTIONARY_LIMIT",
                f"术语词典最多支持 {MAX_TERMINOLOGY_RULES} 条规则。",
            )
        if not isinstance(rule, CorrectionRule):
            raise TypeError("rules must contain only CorrectionRule values")
        for field_name in ("rule_id", "source", "replacement", "note"):
            value = getattr(rule, field_name)
            if not isinstance(value, str):
                raise TypeError(f"CorrectionRule.{field_name} must be a string")
            character_count += len(value)
            if character_count > MAX_TERMINOLOGY_DICTIONARY_BYTES:
                raise ResourceLimitError(
                    "TERMINOLOGY_DICTIONARY_LIMIT",
                    "术语词典文本总量超过安全上限；请精简规则和备注。",
                )
            try:
                byte_count += len(value.encode("utf-8"))
            except UnicodeEncodeError:
                raise ValueError("correction rules must contain valid UTF-8 text") from None
            if byte_count > MAX_TERMINOLOGY_DICTIONARY_BYTES:
                raise ResourceLimitError(
                    "TERMINOLOGY_DICTIONARY_LIMIT",
                    "术语词典 UTF-8 大小超过安全上限；请精简规则和备注。",
                )
        collected.append(rule)
    return tuple(collected)


def _build_match_trie(rules: tuple[CorrectionRule, ...]) -> _TrieNode:
    root = _TrieNode()
    node_count = 1
    for rule in rules:
        node = root
        for character in rule.source:
            child = node.children.get(character)
            if child is None:
                if node_count >= MAX_TERMINOLOGY_TRIE_NODES:
                    raise ResourceLimitError(
                        "TERMINOLOGY_DICTIONARY_LIMIT",
                        "术语词典匹配结构超过安全大小；请缩短或精简规则。",
                    )
                child = _TrieNode()
                node.children[character] = child
                node_count += 1
            node = child
        node.rule = rule
    return root


def _validate_rules(rules: tuple[CorrectionRule, ...]) -> None:
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    for rule in rules:
        if not isinstance(rule, CorrectionRule):
            raise TypeError("rules must contain only CorrectionRule values")
        if rule.rule_id in seen_ids:
            raise ValueError(f"duplicate correction rule id: {rule.rule_id}")
        if rule.source in seen_sources:
            raise ValueError(f"duplicate correction source: {rule.source}")
        seen_ids.add(rule.rule_id)
        seen_sources.add(rule.source)


def _ruleset_fingerprint(rules: tuple[CorrectionRule, ...]) -> str:
    payload = [
        {
            "rule_id": rule.rule_id,
            "source": rule.source,
            "replacement": rule.replacement,
            "note": rule.note,
        }
        for rule in sorted(rules, key=lambda item: item.rule_id)
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _has_safe_boundaries(text: str, start: int, source: str) -> bool:
    end = start + len(source)
    if source[0].isascii() and _is_ascii_word_character(source[0]):
        if start and _is_ascii_word_character(text[start - 1]):
            return False
    if source[-1].isascii() and _is_ascii_word_character(source[-1]):
        if end < len(text) and _is_ascii_word_character(text[end]):
            return False
    return True


def _is_ascii_word_character(value: str) -> bool:
    return value.isascii() and (value.isalnum() or value == "_")

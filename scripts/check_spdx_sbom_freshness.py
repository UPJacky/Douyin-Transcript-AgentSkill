#!/usr/bin/env python3
"""Check that the committed SPDX document renders current lock/evidence inputs.

This check does not read artifact-cache bytes. It validates lock/evidence bindings
and deterministic SPDX output; run verify_spdx_evidence.py when the complete
SHA-256-keyed artifact cache is available to revalidate member bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import generate_spdx_sbom as generator
from spdx_terminal_safety import escape_terminal_controls

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "skills" / "douyin-transcript" / "uv.lock"
DEFAULT_EVIDENCE = ROOT / "docs" / "third-party-license-evidence.json"
DEFAULT_SBOM = ROOT / "docs" / "third-party-sbom.spdx.json"
_CREATED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_CREATION_COMMENT = (
    "Inventory of every package record in uv.lock, including platform marker "
    "variants, optional extras, and development dependencies. licenseDeclared "
    "uses valid SPDX expressions from exact locked artifact author metadata, "
    "license-file evidence tied to exact artifacts in uv.lock, or a reviewed "
    "version-specific legacy-value mapping recorded in "
    "docs/third-party-license-evidence.json; unresolved declarations and every "
    "licenseConcluded remain NOASSERTION pending review."
)


class FreshnessError(ValueError):
    """Raised when the SPDX inventory is malformed or out of date."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FreshnessError("JSON input contains a duplicate object key")
        result[key] = value
    return result


def _load_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise FreshnessError(f"{label} is not valid bounded UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise FreshnessError(f"{label} root must be an object")
    return value


def _created_timestamp(document: dict[str, Any]) -> str:
    creation = document.get("creationInfo")
    if not isinstance(creation, dict):
        raise FreshnessError("SPDX creationInfo is missing")
    created = creation.get("created")
    if not isinstance(created, str) or not _CREATED.fullmatch(created):
        raise FreshnessError("SPDX creation timestamp must be UTC seconds ending in Z")
    try:
        parsed = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise FreshnessError("SPDX creation timestamp is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != created:
        raise FreshnessError("SPDX creation timestamp is not canonical")
    return created


def _strict_inputs(lock_path: Path, evidence_path: Path, sbom_path: Path):
    lock_bytes = generator._read_bounded_bytes(
        lock_path, generator._MAX_LOCK_FILE_BYTES, "uv.lock"
    )
    evidence_bytes = generator._read_bounded_bytes(
        evidence_path, generator._MAX_EVIDENCE_FILE_BYTES, "license evidence"
    )
    sbom_bytes = generator._read_bounded_bytes(
        sbom_path, generator._MAX_EVIDENCE_FILE_BYTES, "SPDX document"
    )
    evidence_document = _load_json_bytes(evidence_bytes, "License evidence")
    spdx_document = _load_json_bytes(sbom_bytes, "SPDX document")
    try:
        lock_document = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise FreshnessError("uv.lock is not valid UTF-8 TOML") from exc
    if not isinstance(lock_document, dict):
        raise FreshnessError("uv.lock root must be a table")
    return (
        lock_bytes,
        lock_document,
        evidence_bytes,
        evidence_document,
        sbom_bytes,
        spdx_document,
    )


def _expected_relationships(
    packages: list[dict[str, Any]],
    evidence_by_package: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, str]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        by_name.setdefault(generator._canonical_name(package["name"]), []).append(
            package
        )

    roots = [
        package for package in packages if package.get("source", {}).get("editable")
    ]
    if len(roots) != 1:
        raise FreshnessError("Expected exactly one editable root package in uv.lock")
    root = roots[0]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": generator._package_id(root),
        }
    ]
    playwright = evidence_by_package.get(("playwright", "1.63.0"))
    npm_packages = (
        playwright.get("_validated_bundled_npm_packages", []) if playwright else []
    )
    if npm_packages:
        playwright_lock = next(
            (
                package
                for package in packages
                if generator._canonical_name(package["name"]) == "playwright"
                and package["version"] == "1.63.0"
            ),
            None,
        )
        if playwright_lock is None:
            raise FreshnessError("Playwright sidecar evidence is not tied to uv.lock")
        relationships.extend(
            {
                "spdxElementId": generator._package_id(playwright_lock),
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": generator._npm_package_id(component),
            }
            for component in npm_packages
        )

    def add_dependencies(
        parent: dict[str, Any],
        dependencies: list[dict[str, Any]],
        group: str | None = None,
    ) -> None:
        for dependency in dependencies:
            targets = by_name.get(generator._canonical_name(dependency["name"]), [])
            wanted_version = dependency.get("version")
            wanted_source = dependency.get("source")
            if wanted_version:
                targets = [
                    item for item in targets if item["version"] == wanted_version
                ]
            if wanted_source:
                targets = [
                    item for item in targets if item.get("source") == wanted_source
                ]
            if not targets:
                raise FreshnessError("uv.lock contains an unresolved dependency target")
            comments: list[str] = []
            if group:
                comments.append(f"uv group/extra: {group}")
            if dependency.get("marker"):
                comments.append(f"uv marker: {dependency['marker']}")
            for target in targets:
                relationship: dict[str, str] = {
                    "spdxElementId": generator._package_id(parent),
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": generator._package_id(target),
                }
                if comments:
                    relationship["comment"] = "; ".join(comments)
                relationships.append(relationship)

    for package in packages:
        add_dependencies(package, package.get("dependencies", []))
        if package is root:
            for extra, dependencies in package.get("optional-dependencies", {}).items():
                add_dependencies(package, dependencies, f"extra:{extra}")
            for group, dependencies in package.get("dev-dependencies", {}).items():
                add_dependencies(package, dependencies, f"dev:{group}")
    return relationships


def build_expected_document(
    lock_path: Path,
    evidence_path: Path,
    lock_bytes: bytes,
    lock: dict[str, Any],
    evidence_bytes: bytes,
    evidence: dict[str, Any],
    created: str,
) -> dict[str, Any]:
    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        raise FreshnessError("uv.lock has no package records")
    generator._validate_package_identity_fields(packages)
    generator._validate_evidence_package_identity_fields(evidence_bytes)
    # The generator validates evidence-to-lock artifact identities and member
    # declarations here. Unlike the full verifier, this does not hash archive bytes.
    evidence_by_package, _ = generator._license_evidence_by_package(
        packages, evidence_bytes, evidence_path
    )
    if evidence.get("packages") != json.loads(
        evidence_bytes.decode("utf-8"), object_pairs_hook=_unique_object
    ).get("packages"):
        raise FreshnessError("License evidence parser results disagree")

    package_records = [
        generator._package_record(
            package,
            evidence_by_package.get(
                (generator._canonical_name(package["name"]), package["version"])
            ),
        )
        for package in packages
    ]
    playwright_evidence = evidence_by_package.get(("playwright", "1.63.0"))
    npm_packages = (
        playwright_evidence.get("_validated_bundled_npm_packages", [])
        if playwright_evidence
        else []
    )
    if npm_packages:
        playwright_lock = next(
            (
                package
                for package in packages
                if generator._canonical_name(package["name"]) == "playwright"
                and package["version"] == "1.63.0"
            ),
            None,
        )
        if playwright_lock is None:
            raise FreshnessError("Playwright sidecar evidence is not tied to uv.lock")
        package_records.extend(
            generator._npm_package_record(
                component, playwright_evidence["artifact_sha256"]
            )
            for component in npm_packages
        )

    lock_digest = hashlib.sha256(lock_bytes).hexdigest()
    evidence_digest = hashlib.sha256(evidence_bytes).hexdigest()
    generator_digest = hashlib.sha256(Path(generator.__file__).read_bytes()).hexdigest()
    namespace_digest = hashlib.sha256(
        f"{lock_digest}\0{evidence_digest}\0{generator_digest}\0{created}".encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "douyin-transcript-uv-lock-all-platforms-extras-and-dev",
        "documentNamespace": f"https://spdx.org/spdxdocs/douyin-transcript-uv-lock-{namespace_digest}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: scripts/generate_spdx_sbom.py"],
            "comment": _CREATION_COMMENT,
        },
        "packages": package_records,
        "relationships": _expected_relationships(packages, evidence_by_package),
    }


def verify_spdx_sbom_freshness(
    lock_path: Path, evidence_path: Path, sbom_path: Path
) -> int:
    (
        lock_bytes,
        lock,
        evidence_bytes,
        evidence,
        sbom_bytes,
        actual,
    ) = _strict_inputs(lock_path, evidence_path, sbom_path)
    created = _created_timestamp(actual)
    expected = build_expected_document(
        lock_path,
        evidence_path,
        lock_bytes,
        lock,
        evidence_bytes,
        evidence,
        created,
    )
    expected_bytes = (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if actual != expected or sbom_bytes != expected_bytes:
        changed = sorted(
            key
            for key in set(actual) | set(expected)
            if actual.get(key) != expected.get(key)
        )
        fields = ", ".join(changed) or "serialized document"
        raise FreshnessError(f"SPDX document is stale or modified ({fields})")
    return len(expected["packages"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--document", type=Path, default=DEFAULT_SBOM)
    args = parser.parse_args(argv)
    try:
        package_count = verify_spdx_sbom_freshness(
            args.lockfile, args.evidence, args.document
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
    ) as exc:
        print(
            f"SPDX freshness check failed: {escape_terminal_controls(str(exc))}",
            file=sys.stderr,
        )
        return 1
    print(
        f"SPDX freshness check passed: {package_count} packages rendered from current lock/evidence"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

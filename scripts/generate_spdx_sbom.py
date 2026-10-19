#!/usr/bin/env python3
"""Generate a whole-lock SPDX 2.3 JSON inventory from uv.lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence
from urllib.parse import quote

from packaging.version import InvalidVersion, Version

from spdx_terminal_safety import contains_terminal_controls, escape_terminal_controls
from safe_output import write_atomic_text

_SPDX_LICENSE_IDS = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC0-1.0",
        "BlueOak-1.0.0",
        "ISC",
        "MIT",
        "MPL-2.0",
        "NCSA",
        "PSF-2.0",
        "Zlib",
    }
)
_SPDX_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*|[()]")
_PYPI_NAME = re.compile(
    r"(?:[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])\Z",
    re.ASCII,
)
_PYPI_VERSION = re.compile(
    r"""
    v?
    (?:(?:[0-9]+)!)?
    [0-9]+(?:\.[0-9]+)*
    (?:[-_.]?(?:alpha|a|beta|b|preview|pre|c|rc)[-_.]?[0-9]*)?
    (?:-(?:[0-9]+)|[-_.]?(?:post|rev|r)[-_.]?[0-9]*)?
    (?:[-_.]?dev[-_.]?[0-9]*)?
    (?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?
    \Z
    """,
    re.IGNORECASE | re.ASCII | re.VERBOSE,
)
_MAX_LOCK_FILE_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_PACKAGES = 5_000
_MAX_EVIDENCE_MEMBERS = 5_000
_MAX_SPDX_EXPRESSION_CHARS = 65_536
_MAX_SPDX_EXPRESSION_TOKENS = 4_096
_MAX_SPDX_EXPRESSION_DEPTH = 64
_VERIFIER_MODULE_NAME = "_douyin_transcript_spdx_evidence_verifier"
_PLAYWRIGHT_WHEEL_SHA256 = (
    "2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6"
)
_REVIEWED_PLAYWRIGHT_NPM_SIDECARS = {
    "playwright/driver/package/lib/serverRegistry.js.LICENSE": (
        "3098a6efcbc11752cbdf6075fa65480f5470f78c8d981fab9c0796dc9a41cefe",
        2982,
        "c9b8515ed7dd5118d0cb47fa5c0f7e9c9e3ab14fb0e3ded97b362ff368ff5eb0",
    ),
    "playwright/driver/package/lib/utilsBundle.js.LICENSE": (
        "2495f30be29620d54b58339821eda0ebabdfb6ee9b09455f7285a06fd46fb9f3",
        106591,
        "6d112956f21aefb17bcd688f32dc774b510e72898ee035e532a1eada1465cd08",
    ),
}
_REVIEWED_PLAYWRIGHT_WEBP_NOTE = (
    "playwright/driver/package/lib/webp_codec.LICENSE",
    "995c7ee35aceb7666829b7a501ca89c0864e12b493c1174b155774ab1e03d831",
    8841,
    "4d2c4dcfd2537360b29a78e7cc23f6ceee687939c78ca3f2182692376c569f09",
)
_REVIEWED_LICENSE_FILE_ASSERTIONS = {
    (
        "colorama",
        "0.4.6",
        "wheel",
        "4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6",
        "colorama-0.4.6.dist-info/licenses/LICENSE.txt",
        "cac35c02686e5d04a5a7140bfb3b36e73aed496656e891102e428886d7930318",
    ): (
        "BSD-3-Clause",
        "The license text carries BSD-3-Clause terms; the declaration describes Colorama and does not conclude licenses for other components.",
    ),
    (
        "editables",
        "0.5",
        "wheel",
        "61e5ffa82629e0d8bfe09bc44a07db3c1ab8ed1ce78a6980732870f19b5e7d4c",
        "editables-0.5.dist-info/LICENSE.txt",
        "c73e08a04e1557fdb49525fb7a579f73bcab84a254910b9350ee56daf143932d",
    ): (
        "MIT",
        "The wheel LICENSE.txt contains MIT terms; the declaration describes editables only and does not conclude licenses for other components.",
    ),
    (
        "onnxruntime",
        "1.30.0",
        "wheel",
        "0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7",
        "onnxruntime/LICENSE",
        "c250d6278f0b47a6439fb7592b08b58a55eb9f535aa49a1db63211c3f982b674",
    ): (
        "MIT",
        "The wheel also includes ThirdPartyNotices.txt (SHA-256 c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622); its component notices have not been mapped to linked binaries.",
    ),
    (
        "ruff",
        "0.14.14",
        "wheel",
        "3dde1435e6b6fe5b66506c1dff67a421d0b7f6488d466f651c07f4cab3bf20fd",
        "ruff-0.14.14.dist-info/licenses/LICENSE",
        "2597d854122b77ddc71971564ca2350a37608575ce324adc5650a2b2051c8f18",
    ): (
        "MIT",
        "The wheel LICENSE supports MIT for Ruff; Rust dependency licenses and notices have not been reviewed.",
    ),
    (
        "pathspec",
        "1.1.1",
        "wheel",
        "a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189",
        "pathspec-1.1.1.dist-info/licenses/LICENSE",
        "fab3dd6bdab226f1c08630b1dd917e11fcb4ec5e1e020e2c16f83a0a13863e85",
    ): (
        "MPL-2.0",
        "The wheel LICENSE contains Mozilla Public License 2.0 terms; the declaration describes pathspec only and does not conclude licenses for other components.",
    ),
    (
        "playwright",
        "1.63.0",
        "wheel",
        "2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6",
        "playwright-1.63.0.dist-info/licenses/LICENSE",
        "7fab1461b41970ff376f1c9303a637076bfaaeb71cd12dd3a1c44aaf59a1a2b9",
    ): (
        "Apache-2.0",
        "The locked wheel LICENSE supports the Playwright Apache-2.0 declaration. Across all 8 locked platform wheels, 64 license/notice-like members were checked against their archive bytes and RECORD entries; the ThirdPartyNotices file describes adjacent JavaScript bundle license sidecars, and the driver has a separate Node license inventory. This verifies file presence and integrity only; it does not conclude component licensing or distribution obligations.",
    ),
    (
        "python-dateutil",
        "2.9.0.post0",
        "sdist",
        "37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3",
        "python-dateutil-2.9.0.post0/LICENSE",
        "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
    ): (
        "BSD-3-Clause",
        "The exact locked sdist LICENSE states that BSD terms apply to all code, including code also covered by Apache 2.0. This records the package-wide BSD-3-Clause option; it does not conclude bundled-component or redistribution obligations.",
    ),
    (
        "trove-classifiers",
        "2026.9.21.13",
        "wheel",
        "8b1ff4f9c191b1040b71c37f1e445ab99732911e3cd91de52838453a854d7a17",
        "trove_classifiers-2026.9.21.13.dist-info/licenses/LICENSE",
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    ): (
        "Apache-2.0",
        "The wheel LICENSE contains Apache License 2.0 terms; the declaration describes trove-classifiers only and does not conclude licenses for other components.",
    ),
    (
        "tokenizers",
        "0.23.2",
        "sdist",
        "7f0f085686b9de0d0079e6f874ae053600db64c5d13049e0bbc0119926d25aac",
        "tokenizers-0.23.2/tokenizers/LICENSE",
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    ): (
        "Apache-2.0",
        "The source archive LICENSE states Apache License 2.0; Rust dependency licenses and notices in the built wheel have not been reviewed.",
    ),
}
_REVIEWED_LEGACY_LICENSE_MAPPINGS = {
    (
        "flatbuffers",
        "25.12.19",
        "License",
        "Apache 2.0",
        "9f38239f96faa21522a6aadab6912e1e560708bbe9c9f696a0679c9403fa089e",
        "7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4",
    ): {
        "expression": "Apache-2.0",
        "sources": [
            "https://pypi.org/project/flatbuffers/25.12.19/",
            "https://github.com/google/flatbuffers/blob/v25.12.19/python/setup.py",
            "https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE",
        ],
    }
}


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_pypi_version(version: object) -> str | None:
    if not isinstance(version, str) or _PYPI_VERSION.fullmatch(version) is None:
        return None
    try:
        parsed = Version(version)
    except InvalidVersion:
        return None
    # Version.__str__ removes aliases such as a leading "v", alternate
    # separators, and case differences while preserving the locked release
    # segment (for example, 1.0.0 remains 1.0.0).
    return str(parsed)


def _valid_pypi_identity(name: object, version: object) -> bool:
    return (
        isinstance(name, str)
        and _PYPI_NAME.fullmatch(name) is not None
        and _canonical_pypi_version(version) is not None
    )


def _pypi_purl(name: str, version: str) -> str:
    canonical_version = _canonical_pypi_version(version)
    if (
        not isinstance(name, str)
        or _PYPI_NAME.fullmatch(name) is None
        or canonical_version is None
    ):
        raise ValueError("uv.lock contains an invalid package name or version")
    # PURL path components use percent encoding; in particular, '+' must not
    # remain literal, and delimiters must never alter the package identity.
    # Normalize accepted PEP 440 aliases before encoding so equal PyPI releases
    # cannot acquire different PURLs from alternate spellings.
    return (
        f"pkg:pypi/{quote(_canonical_name(name), safe='-._~')}"
        f"@{quote(canonical_version, safe='-._~')}"
    )


def _validate_package_identity_fields(packages: object) -> None:
    if not isinstance(packages, list) or not packages:
        raise ValueError("uv.lock contains invalid package records")
    normalized_identities: set[tuple[str, Version]] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("uv.lock contains an invalid package record")
        name = package.get("name")
        version = package.get("version")
        if (
            not _valid_pypi_identity(name, version)
            or contains_terminal_controls(name)
            or contains_terminal_controls(version)
        ):
            raise ValueError("uv.lock contains an invalid package name or version")
        identity = (_canonical_name(name), Version(version))
        if identity in normalized_identities:
            raise ValueError("uv.lock contains duplicate normalized package identities")
        normalized_identities.add(identity)


def _validate_evidence_package_identity_fields(evidence_bytes: bytes) -> None:
    try:
        document = json.loads(evidence_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        return
    if not isinstance(document, dict) or not isinstance(document.get("packages"), list):
        return
    normalized_identities: set[tuple[str, Version]] = set()
    for package in document["packages"]:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            canonical_version = _canonical_pypi_version(version)
            if (
                canonical_version is None
                or _PYPI_NAME.fullmatch(name) is None
                or contains_terminal_controls(name)
                or contains_terminal_controls(version)
            ):
                raise ValueError(
                    "License evidence contains an invalid package name or version"
                )
            identity = (_canonical_name(name), Version(version))
            if identity in normalized_identities:
                raise ValueError(
                    "License evidence contains duplicate normalized package identities"
                )
            normalized_identities.add(identity)


def _package_id(package: dict[str, Any]) -> str:
    identity = "\0".join(
        (
            package["name"],
            package["version"],
            json.dumps(package.get("source", {}), sort_keys=True),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"SPDXRef-Package-{digest}"


def _valid_spdx_expression(expression: str) -> bool:
    if not isinstance(expression, str) or len(expression) > _MAX_SPDX_EXPRESSION_CHARS:
        return False

    tokens: list[str] = []
    cursor = 0
    for match in _SPDX_TOKEN.finditer(expression):
        if expression[cursor : match.start()].strip():
            return False
        tokens.append(match.group())
        if len(tokens) > _MAX_SPDX_EXPRESSION_TOKENS:
            return False
        cursor = match.end()
    if expression[cursor:].strip() or not tokens:
        return False

    position = 0

    def parse_primary(depth: int = 0) -> bool:
        nonlocal position
        if position >= len(tokens):
            return False
        token = tokens[position]
        if token == "(":
            if depth >= _MAX_SPDX_EXPRESSION_DEPTH:
                return False
            position += 1
            if (
                not parse_or_expression(depth + 1)
                or position >= len(tokens)
                or tokens[position] != ")"
            ):
                return False
            position += 1
            return True
        if token not in _SPDX_LICENSE_IDS:
            return False
        position += 1
        return True

    def parse_and_expression(depth: int = 0) -> bool:
        nonlocal position
        if not parse_primary(depth):
            return False
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            if not parse_primary(depth):
                return False
        return True

    def parse_or_expression(depth: int = 0) -> bool:
        nonlocal position
        if not parse_and_expression(depth):
            return False
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            if not parse_and_expression(depth):
                return False
        return True

    return parse_or_expression() and position == len(tokens)


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_playwright_bundled_evidence(
    key: tuple[str, str],
    evidence: dict[str, Any],
    package: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    sidecars = evidence.get("artifact_bound_npm_sidecars")
    webp_note = evidence.get("webp_codec_component_note")
    if key != ("playwright", "1.63.0"):
        if sidecars is not None or webp_note is not None:
            raise ValueError(
                f"Bundled Playwright evidence is attached to an unexpected package: {key}"
            )
        return [], False
    if not isinstance(sidecars, list) or not isinstance(webp_note, dict):
        raise ValueError("Playwright bundled npm and WebP evidence is missing")
    if package.get("name") != "playwright" or package.get("version") != "1.63.0":
        raise ValueError(
            "Playwright bundled evidence does not match its locked package"
        )

    artifact_url = evidence.get("artifact_url")
    artifact_sha256 = evidence.get("artifact_sha256")
    artifact_size = evidence.get("artifact_size")
    if (
        artifact_sha256 != _PLAYWRIGHT_WHEEL_SHA256
        or not isinstance(artifact_url, str)
        or not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
    ):
        raise ValueError(
            "Playwright bundled evidence is not bound to the reviewed Windows x64 wheel"
        )
    if not any(
        artifact.get("url") == artifact_url
        and artifact.get("hash") == f"sha256:{artifact_sha256}"
        and artifact.get("size") == artifact_size
        for artifact in package.get("wheels", [])
    ):
        raise ValueError(
            "Playwright bundled evidence artifact is not pinned by uv.lock"
        )

    artifact_members = evidence.get("artifact_members", [])

    def require_member(path: str, digest: str, size: int) -> None:
        if not any(
            isinstance(member, dict)
            and member.get("artifact_type") == "wheel"
            and member.get("artifact_url") == artifact_url
            and member.get("artifact_sha256") == artifact_sha256
            and member.get("artifact_size") == artifact_size
            and member.get("path") == path
            and member.get("sha256") == digest
            and member.get("size") == size
            for member in artifact_members
        ):
            raise ValueError(
                f"Bundled Playwright sidecar is not tied to a verified artifact member: {path}"
            )

    if len(sidecars) != len(_REVIEWED_PLAYWRIGHT_NPM_SIDECARS):
        raise ValueError("Unexpected Playwright npm sidecar count")
    packages_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    seen_sidecars: set[str] = set()
    textless: list[tuple[str, str]] = []
    for sidecar in sidecars:
        if not isinstance(sidecar, dict):
            raise ValueError("Invalid Playwright npm sidecar evidence")
        path = sidecar.get("member_path")
        reviewed = _REVIEWED_PLAYWRIGHT_NPM_SIDECARS.get(path)
        if reviewed is None or path in seen_sidecars:
            raise ValueError("Unreviewed or duplicate Playwright npm sidecar")
        seen_sidecars.add(path)
        digest, size, catalog_digest = reviewed
        if (
            sidecar.get("artifact_type") != "wheel"
            or sidecar.get("artifact_url") != artifact_url
            or sidecar.get("artifact_sha256") != artifact_sha256
            or sidecar.get("artifact_size") != artifact_size
            or sidecar.get("member_sha256") != digest
            or sidecar.get("member_size") != size
            or _canonical_json_sha256(sidecar.get("packages")) != catalog_digest
        ):
            raise ValueError(
                f"Playwright npm sidecar catalog differs from reviewed evidence: {path}"
            )
        require_member(path, digest, size)
        components = sidecar.get("packages")
        if not isinstance(components, list):
            raise ValueError(
                f"Invalid package catalog in Playwright npm sidecar: {path}"
            )
        local_keys: set[tuple[str, str]] = set()
        for component in components:
            if not isinstance(component, dict) or set(component) != {
                "name",
                "version",
                "license_expression",
                "license_basis",
            }:
                raise ValueError(
                    f"Invalid package entry in Playwright npm sidecar: {path}"
                )
            name = component.get("name")
            version = component.get("version")
            expression = component.get("license_expression")
            basis = component.get("license_basis")
            if (
                not isinstance(name, str)
                or len(name) > 214
                or not re.fullmatch(
                    r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*", name
                )
                or not isinstance(version, str)
                or not re.fullmatch(
                    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
                    version,
                )
                or not isinstance(expression, str)
                or not _valid_spdx_expression(expression)
                or not isinstance(basis, str)
                or basis not in {"license_text", "declared_without_license_text"}
            ):
                raise ValueError(f"Invalid Playwright npm package evidence in {path}")
            package_key = (name, version)
            if package_key in local_keys:
                raise ValueError(
                    f"Duplicate npm package in Playwright sidecar: {package_key}"
                )
            local_keys.add(package_key)
            if basis == "declared_without_license_text":
                if (
                    package_key != ("proxy-agent-negotiate", "1.1.0")
                    or expression != "MIT"
                ):
                    raise ValueError(
                        f"Unexpected textless npm license declaration: {package_key}"
                    )
                textless.append(package_key)
            prior = packages_by_key.get(package_key)
            if prior is None:
                prior = {
                    **component,
                    "evidence_sidecars": [],
                }
                packages_by_key[package_key] = prior
            elif (
                prior["license_expression"] != expression
                or prior["license_basis"] != basis
            ):
                raise ValueError(
                    f"Conflicting license evidence for bundled npm package: {package_key}"
                )
            prior["evidence_sidecars"].append(
                {"path": path, "sha256": digest, "size": size}
            )
    if seen_sidecars != set(_REVIEWED_PLAYWRIGHT_NPM_SIDECARS):
        raise ValueError("Playwright npm sidecar inventory is incomplete")
    if len(packages_by_key) != 79 or textless != [("proxy-agent-negotiate", "1.1.0")]:
        raise ValueError(
            "Playwright npm package inventory does not match reviewed sidecar counts"
        )
    if (
        sum(
            item["license_basis"] == "license_text" for item in packages_by_key.values()
        )
        != 78
    ):
        raise ValueError(
            "Playwright npm sidecar license-text count differs from reviewed evidence"
        )

    webp_path, webp_digest, webp_size, webp_catalog_digest = (
        _REVIEWED_PLAYWRIGHT_WEBP_NOTE
    )
    if (
        webp_note.get("artifact_type") != "wheel"
        or webp_note.get("artifact_url") != artifact_url
        or webp_note.get("artifact_sha256") != artifact_sha256
        or webp_note.get("artifact_size") != artifact_size
        or webp_note.get("member_path") != webp_path
        or webp_note.get("member_sha256") != webp_digest
        or webp_note.get("member_size") != webp_size
        or _canonical_json_sha256(webp_note) != webp_catalog_digest
    ):
        raise ValueError(
            "Playwright WebP sidecar note differs from reviewed artifact evidence"
        )
    require_member(webp_path, webp_digest, webp_size)
    return sorted(
        packages_by_key.values(), key=lambda item: (item["name"], item["version"])
    ), True


def _read_bounded_bytes(path: Path, maximum: int, label: str) -> bytes:
    try:
        path_info = path.lstat()
    except OSError:
        raise
    if stat.S_ISLNK(path_info.st_mode) or not stat.S_ISREG(path_info.st_mode):
        raise ValueError(f"{label} must be a regular, non-symlink file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        descriptor = stream.fileno()
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if (initial.st_dev, initial.st_ino) != (path_info.st_dev, path_info.st_ino):
            raise ValueError(f"{label} changed between validation and open")
        if initial.st_size > maximum:
            raise ValueError(f"{label} exceeds {maximum} byte size limit")
        content = stream.read(maximum + 1)
        if len(content) > maximum:
            raise ValueError(f"{label} exceeds {maximum} byte size limit")
        final = os.fstat(descriptor)
        if (
            initial.st_dev,
            initial.st_ino,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        ) != (
            final.st_dev,
            final.st_ino,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            raise ValueError(f"{label} changed while being read")
    return content


def _verified_evidence_summary(
    lock_path: Path,
    evidence_path: Path,
    artifact_cache_dir: Path,
    lock_bytes: bytes,
    evidence_bytes: bytes,
) -> Any:
    module = sys.modules.get(_VERIFIER_MODULE_NAME)
    if module is None:
        verifier_path = Path(__file__).resolve().with_name("verify_spdx_evidence.py")
        spec = importlib.util.spec_from_file_location(
            _VERIFIER_MODULE_NAME, verifier_path
        )
        if spec is None or spec.loader is None:
            raise ValueError("Could not load the SPDX evidence verifier")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_VERIFIER_MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(_VERIFIER_MODULE_NAME, None)
            raise
    return module.verify_evidence(
        lock_path,
        evidence_path,
        artifact_cache_dir,
        lock_bytes=lock_bytes,
        evidence_bytes=evidence_bytes,
    )


def _license_evidence_by_package(
    packages: list[dict[str, Any]], evidence_bytes: bytes, evidence_path: Path
) -> tuple[dict[tuple[str, str], dict[str, Any]], bytes]:
    try:
        document = json.loads(evidence_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"Invalid license evidence document: {evidence_path}") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or not isinstance(document.get("packages"), list)
    ):
        raise ValueError(f"Unsupported license evidence document: {evidence_path}")
    if len(document["packages"]) > _MAX_EVIDENCE_PACKAGES:
        raise ValueError(
            f"License evidence exceeds {_MAX_EVIDENCE_PACKAGES} package row limit"
        )

    package_by_key = {
        (_canonical_name(package["name"]), package["version"]): package
        for package in packages
        if not package.get("source", {}).get("editable")
    }
    evidence_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    evidence_member_count = 0
    for evidence in document["packages"]:
        if not isinstance(evidence, dict):
            raise ValueError("Every license evidence package row must be an object")
        if (
            not isinstance(evidence.get("name"), str)
            or not evidence["name"]
            or contains_terminal_controls(evidence["name"])
            or not isinstance(evidence.get("version"), str)
            or not evidence["version"]
            or contains_terminal_controls(evidence["version"])
        ):
            raise ValueError(
                "License evidence row has an invalid package name or version"
            )
        key = (_canonical_name(evidence["name"]), evidence["version"])
        if key in evidence_by_key:
            raise ValueError(f"Duplicate license evidence for {key[0]} {key[1]}")
        package = package_by_key.get(key)
        if package is None:
            raise ValueError(
                f"License evidence does not match uv.lock: {key[0]} {key[1]}"
            )

        artifact_type = evidence.get("artifact_type")
        if artifact_type == "sdist":
            artifacts = [package["sdist"]] if package.get("sdist") else []
        elif artifact_type == "wheel":
            artifacts = package.get("wheels", [])
        else:
            raise ValueError(f"Invalid artifact type in license evidence for {key}")
        expected_artifact = next(
            (
                artifact
                for artifact in artifacts
                if artifact.get("url") == evidence.get("artifact_url")
                and artifact.get("hash") == f"sha256:{evidence.get('artifact_sha256')}"
                and artifact.get("size") == evidence.get("artifact_size")
            ),
            None,
        )
        if expected_artifact is None:
            raise ValueError(
                f"Artifact in license evidence is not pinned by uv.lock: {key}"
            )

        metadata_hash = evidence.get("metadata_sha256")
        if not isinstance(metadata_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", metadata_hash
        ):
            raise ValueError(f"Invalid metadata SHA-256 in license evidence for {key}")
        field = evidence.get("metadata_field")
        value = evidence.get("metadata_field_value")
        expression = evidence.get("declared_expression")
        mapped_expression = evidence.get("mapped_expression")
        status = evidence.get("status")
        if status == "valid_spdx_declaration":
            if (
                field not in {"License", "License-Expression"}
                or not isinstance(value, str)
                or expression != value
                or mapped_expression is not None
                or not _valid_spdx_expression(expression)
            ):
                raise ValueError(f"Invalid SPDX declaration evidence for {key}")
        elif status == "no_license_field":
            if (
                field is not None
                or value is not None
                or expression is not None
                or mapped_expression is not None
            ):
                raise ValueError(f"Inconsistent missing-license evidence for {key}")
        elif status == "legacy_value_not_spdx_expression":
            if (
                field not in {"License", "License-Expression"}
                or not isinstance(value, str)
                or expression is not None
                or mapped_expression is not None
                or _valid_spdx_expression(value)
            ):
                raise ValueError(f"Inconsistent legacy-license evidence for {key}")
        elif status == "reviewed_legacy_value_mapping":
            if not isinstance(field, str) or not isinstance(value, str):
                raise ValueError(f"Invalid legacy-license mapping evidence for {key}")
            mapping_key = (
                key[0],
                key[1],
                field,
                value,
                metadata_hash,
                evidence.get("artifact_sha256"),
            )
            approved_mapping = _REVIEWED_LEGACY_LICENSE_MAPPINGS.get(mapping_key)
            supplied_sources = evidence.get("mapping_sources")
            approved_sources = approved_mapping["sources"] if approved_mapping else None
            if (
                field not in {"License", "License-Expression"}
                or not isinstance(value, str)
                or expression is not None
                or approved_mapping is None
                or mapped_expression != approved_mapping["expression"]
                or _valid_spdx_expression(value)
                or supplied_sources != approved_sources
            ):
                raise ValueError(f"Unreviewed legacy-license mapping for {key}")
        elif status == "file_verified_declaration":
            if (
                field not in {None, "License", "License-Expression"}
                or mapped_expression is not None
            ):
                raise ValueError(
                    f"Invalid metadata field for file-level license evidence for {key}"
                )
            if expression is not None:
                raise ValueError(
                    f"File-level license evidence must not reuse metadata declaration for {key}"
                )
        else:
            raise ValueError(f"Invalid license evidence status for {key}")

        license_file = evidence.get("license_file")
        if status == "file_verified_declaration":
            if not isinstance(license_file, dict):
                raise ValueError(f"Missing license-file evidence for {key}")
            file_artifact_type = license_file.get("artifact_type")
            if file_artifact_type == "sdist":
                file_artifacts = [package["sdist"]] if package.get("sdist") else []
            elif file_artifact_type == "wheel":
                file_artifacts = package.get("wheels", [])
            else:
                raise ValueError(f"Invalid license-file artifact type for {key}")
            expected_file_artifact = next(
                (
                    artifact
                    for artifact in file_artifacts
                    if artifact.get("url") == license_file.get("artifact_url")
                    and artifact.get("hash")
                    == f"sha256:{license_file.get('artifact_sha256')}"
                    and artifact.get("size") == license_file.get("artifact_size")
                ),
                None,
            )
            if expected_file_artifact is None:
                raise ValueError(
                    f"License file is not from an artifact pinned by uv.lock: {key}"
                )
            file_path = license_file.get("path")
            file_hash = license_file.get("sha256")
            file_expression = license_file.get("expression")
            if (
                not isinstance(file_path, str)
                or not file_path
                or file_path.startswith(("/", "\\"))
                or PureWindowsPath(file_path).is_absolute()
                or ".." in Path(file_path).parts
                or ".." in PureWindowsPath(file_path).parts
                or not isinstance(file_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", file_hash)
                or not isinstance(file_expression, str)
                or not _valid_spdx_expression(file_expression)
            ):
                raise ValueError(f"Invalid license-file evidence for {key}")
            approved_assertion = _REVIEWED_LICENSE_FILE_ASSERTIONS.get(
                (
                    key[0],
                    key[1],
                    file_artifact_type,
                    license_file["artifact_sha256"],
                    file_path,
                    file_hash,
                )
            )
            if (
                approved_assertion is None
                or approved_assertion[0] != file_expression
                or approved_assertion[1] != license_file.get("review_note")
            ):
                raise ValueError(f"Unreviewed license-file evidence for {key}")
            notices = evidence.get("license_notices", [])
            if not isinstance(notices, list):
                raise ValueError(f"Invalid license notices for {key}")
            for notice in notices:
                if not isinstance(notice, dict):
                    raise ValueError(f"Invalid license notice evidence for {key}")
                notice_type = notice.get("artifact_type")
                if notice_type == "sdist":
                    notice_artifacts = (
                        [package["sdist"]] if package.get("sdist") else []
                    )
                elif notice_type == "wheel":
                    notice_artifacts = package.get("wheels", [])
                else:
                    raise ValueError(f"Invalid license notice artifact type for {key}")
                if not any(
                    artifact.get("url") == notice.get("artifact_url")
                    and artifact.get("hash")
                    == f"sha256:{notice.get('artifact_sha256')}"
                    and artifact.get("size") == notice.get("artifact_size")
                    for artifact in notice_artifacts
                ):
                    raise ValueError(
                        f"License notice is not from a pinned artifact: {key}"
                    )
                notice_path = notice.get("path")
                notice_hash = notice.get("sha256")
                notice_size = notice.get("size")
                if (
                    not isinstance(notice_path, str)
                    or not notice_path
                    or notice_path.startswith(("/", "\\"))
                    or PureWindowsPath(notice_path).is_absolute()
                    or ".." in Path(notice_path).parts
                    or ".." in PureWindowsPath(notice_path).parts
                    or not isinstance(notice_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", notice_hash)
                    or not isinstance(notice_size, int)
                    or isinstance(notice_size, bool)
                    or notice_size < 0
                ):
                    raise ValueError(f"Invalid license notice evidence for {key}")
        elif license_file is not None or evidence.get("license_notices"):
            raise ValueError(f"Unexpected license-file evidence for {key}")

        artifact_members = evidence.get("artifact_members", [])
        if not isinstance(artifact_members, list):
            raise ValueError(f"Invalid supplemental artifact member list for {key}")
        evidence_member_count += len(artifact_members)
        if evidence_member_count > _MAX_EVIDENCE_MEMBERS:
            raise ValueError(
                f"License evidence exceeds {_MAX_EVIDENCE_MEMBERS} supplemental member limit"
            )
        for member in artifact_members:
            if not isinstance(member, dict):
                raise ValueError(f"Invalid supplemental artifact member for {key}")
            member_type = member.get("artifact_type")
            if member_type == "sdist":
                member_artifacts = [package["sdist"]] if package.get("sdist") else []
            elif member_type == "wheel":
                member_artifacts = package.get("wheels", [])
            else:
                raise ValueError(f"Invalid supplemental artifact type for {key}")
            if not any(
                artifact.get("url") == member.get("artifact_url")
                and artifact.get("hash") == f"sha256:{member.get('artifact_sha256')}"
                and artifact.get("size") == member.get("artifact_size")
                for artifact in member_artifacts
            ):
                raise ValueError(
                    f"Supplemental member artifact is not pinned by uv.lock: {key}"
                )
            path = member.get("path")
            digest = member.get("sha256")
            size = member.get("size")
            if (
                not isinstance(path, str)
                or not path
                or path.startswith(("/", "\\"))
                or "\\" in path
                or contains_terminal_controls(path)
                or PureWindowsPath(path).is_absolute()
                or ".." in Path(path).parts
                or ".." in PureWindowsPath(path).parts
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise ValueError(
                    f"Invalid supplemental artifact member evidence for {key}"
                )
        npm_components, has_webp_note = _validate_playwright_bundled_evidence(
            key, evidence, package
        )
        if npm_components:
            evidence["_validated_bundled_npm_packages"] = npm_components
        if has_webp_note:
            evidence["_validated_webp_codec_component_note"] = True
        evidence_by_key[key] = evidence

    if evidence_by_key.keys() != package_by_key.keys():
        missing = sorted(package_by_key.keys() - evidence_by_key.keys())
        raise ValueError(f"License evidence missing locked packages: {missing}")
    return evidence_by_key, evidence_bytes


def _package_record(
    package: dict[str, Any], license_evidence: dict[str, Any] | None
) -> dict[str, Any]:
    name = package["name"]
    version = package["version"]
    source = package.get("source", {})
    source_kind = ", ".join(sorted(source)) or "unspecified"
    artifact_count = len(package.get("wheels", [])) + int("sdist" in package)
    declared_expression = None
    if license_evidence is not None:
        if license_evidence["status"] == "file_verified_declaration":
            declared_expression = license_evidence["license_file"]["expression"]
        elif license_evidence["status"] == "reviewed_legacy_value_mapping":
            declared_expression = license_evidence["mapped_expression"]
        else:
            declared_expression = license_evidence["declared_expression"]
    if license_evidence is None:
        license_comment = (
            "The project license remains unselected by its owner; license conclusion is "
            "NOASSERTION."
        )
    elif license_evidence["status"] == "file_verified_declaration":
        license_file = license_evidence["license_file"]
        license_comment = (
            f"licenseDeclared is supported by {license_file['path']} (SHA-256 "
            f"{license_file['sha256']}) in the locked {license_file['artifact_type']} "
            f"(SHA-256 {license_file['artifact_sha256']}); the artifact is pinned by "
            "uv.lock. licenseConcluded remains NOASSERTION pending review of bundled "
            "components and redistribution obligations. "
            f"{license_file.get('review_note', '')}"
        ).strip()
    elif license_evidence["status"] == "reviewed_legacy_value_mapping":
        sources = ", ".join(license_evidence["mapping_sources"])
        license_comment = (
            f"licenseDeclared maps the exact legacy author metadata value "
            f"{license_evidence['metadata_field']}={license_evidence['metadata_field_value']!r} "
            f"to {declared_expression} under a reviewed, version-specific mapping. "
            f"The metadata entry {license_evidence['metadata_path']} in the locked "
            f"{license_evidence['artifact_type']} has SHA-256 "
            f"{license_evidence['metadata_sha256']}; mapping evidence: {sources}. "
            "licenseConcluded remains NOASSERTION pending review of bundled components "
            "and redistribution obligations."
        )
    elif declared_expression:
        license_comment = (
            f"licenseDeclared is copied unchanged from author metadata field "
            f"{license_evidence['metadata_field']} in the locked "
            f"{license_evidence['artifact_type']} (SHA-256 "
            f"{license_evidence['artifact_sha256']}); metadata entry "
            f"{license_evidence['metadata_path']} has SHA-256 "
            f"{license_evidence['metadata_sha256']}. licenseConcluded remains "
            "NOASSERTION pending file-level and bundled-component review."
        )
    else:
        field = license_evidence["metadata_field"]
        value = license_evidence["metadata_field_value"]
        metadata_detail = (
            "no license field is present"
            if field is None
            else f"legacy field {field} contains {value!r}, which is not a valid SPDX expression"
        )
        license_comment = (
            f"The locked {license_evidence['artifact_type']} metadata entry "
            f"{license_evidence['metadata_path']} (SHA-256 "
            f"{license_evidence['metadata_sha256']}) has {metadata_detail}; "
            "licenseDeclared and licenseConcluded remain NOASSERTION."
        )
    supplemental_count = (
        len(license_evidence.get("artifact_members", [])) if license_evidence else 0
    )
    if supplemental_count:
        license_comment += (
            f" {supplemental_count} additional artifact members with license/notice-like "
            "filenames are byte-verified; see docs/third-party-license-evidence.json. "
            "This records presence and integrity only, not license applicability or conclusion."
        )
    if license_evidence and license_evidence.get(
        "_validated_webp_codec_component_note"
    ):
        license_comment += (
            " The webp_codec sidecar associates unversioned libwebp (BSD-3-Clause) with "
            "webp_codec.wasm and Emscripten (MIT OR NCSA) with its JavaScript glue/runtime. "
            "It also reproduces Node.js and musl MIT notices without versions or a direct "
            "dependency mapping; these notes record sidecar content only. "
            "licenseConcluded remains NOASSERTION."
        )
    return {
        "SPDXID": _package_id(package),
        "name": name,
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": declared_expression or "NOASSERTION",
        "licenseComments": license_comment,
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "APPLICATION" if source.get("editable") else "LIBRARY",
        "sourceInfo": (
            f"uv.lock source kind: {source_kind}; "
            f"locked artifact records: {artifact_count}; dependency marker conditions "
            "are attached to SPDX relationships."
        ),
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": _pypi_purl(name, version),
            }
        ],
    }


def _npm_package_id(component: dict[str, Any]) -> str:
    identity = f"{component['name']}@{component['version']}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"SPDXRef-NpmPackage-{digest}"


def _npm_package_record(component: dict[str, Any], wheel_sha256: str) -> dict[str, Any]:
    sidecar_details = "; ".join(
        f"{source['path']} (SHA-256 {source['sha256']}, {source['size']} bytes)"
        for source in component["evidence_sidecars"]
    )
    if component["license_basis"] == "declared_without_license_text":
        evidence_detail = (
            "The sidecar lists this package with a declared MIT license but contains no license "
            "text for it; licenseDeclared records that declaration only."
        )
    else:
        evidence_detail = (
            f"The sidecar lists {component['license_expression']} and includes associated "
            "license text; this records the artifact's notice evidence."
        )
    return {
        "SPDXID": _npm_package_id(component),
        "name": component["name"],
        "versionInfo": component["version"],
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": component["license_expression"],
        "licenseComments": (
            f"{evidence_detail} Evidence is bound to locked Playwright 1.63.0 Windows x64 wheel "
            f"SHA-256 {wheel_sha256}: {sidecar_details}. licenseConcluded remains NOASSERTION."
        ),
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "LIBRARY",
        "sourceInfo": "Bundled npm package listed in the locked Playwright wheel sidecar evidence.",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": (
                    f"pkg:npm/{quote(component['name'], safe='/.-_~')}@{component['version']}"
                ),
            }
        ],
    }


def build_document(
    lock_path: Path,
    *,
    artifact_cache_dir: Path,
    created: str | None = None,
    license_evidence_path: Path | None = None,
) -> dict[str, Any]:
    lock_bytes = _read_bounded_bytes(lock_path, _MAX_LOCK_FILE_BYTES, "uv.lock")
    lock = tomllib.loads(lock_bytes.decode("utf-8"))
    packages = lock.get("package", [])
    if not packages:
        raise ValueError(f"No packages found in {lock_path}")
    _validate_package_identity_fields(packages)

    evidence_path = license_evidence_path or (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "third-party-license-evidence.json"
    )
    evidence_bytes = _read_bounded_bytes(
        evidence_path, _MAX_EVIDENCE_FILE_BYTES, "License evidence document"
    )
    _validate_evidence_package_identity_fields(evidence_bytes)
    verification = _verified_evidence_summary(
        lock_path,
        evidence_path,
        artifact_cache_dir,
        lock_bytes,
        evidence_bytes,
    )
    if (
        verification.lock_sha256 != hashlib.sha256(lock_bytes).hexdigest()
        or verification.evidence_sha256 != hashlib.sha256(evidence_bytes).hexdigest()
    ):
        raise ValueError(
            "Verified SPDX inputs differ from the generator input snapshot"
        )
    evidence_by_package, evidence_bytes = _license_evidence_by_package(
        packages, evidence_bytes, evidence_path
    )

    ids_by_name: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        ids_by_name.setdefault(_canonical_name(package["name"]), []).append(package)

    package_records = [
        _package_record(
            package,
            evidence_by_package.get(
                (_canonical_name(package["name"]), package["version"])
            ),
        )
        for package in packages
    ]
    playwright_evidence = evidence_by_package.get(("playwright", "1.63.0"))
    bundled_npm_packages = (
        playwright_evidence.get("_validated_bundled_npm_packages", [])
        if playwright_evidence
        else []
    )
    playwright_lock_package = next(
        (
            package
            for package in packages
            if _canonical_name(package["name"]) == "playwright"
            and package["version"] == "1.63.0"
        ),
        None,
    )
    if bundled_npm_packages and playwright_lock_package is None:
        raise ValueError("Playwright sidecar evidence has no matching locked package")
    if playwright_evidence and bundled_npm_packages:
        package_records.extend(
            _npm_package_record(component, playwright_evidence["artifact_sha256"])
            for component in bundled_npm_packages
        )
    relationships: list[dict[str, str]] = []

    root_packages = [
        package for package in packages if package.get("source", {}).get("editable")
    ]
    if len(root_packages) != 1:
        raise ValueError(
            f"Expected one editable project package, found {len(root_packages)}"
        )
    root = root_packages[0]
    root_id = _package_id(root)
    relationships.append(
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_id,
        }
    )
    if bundled_npm_packages and playwright_lock_package is not None:
        relationships.extend(
            {
                "spdxElementId": _package_id(playwright_lock_package),
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": _npm_package_id(component),
            }
            for component in bundled_npm_packages
        )

    def add_dependencies(
        parent: dict[str, Any],
        dependencies: list[dict[str, Any]],
        *,
        group: str | None = None,
    ) -> None:
        for dependency in dependencies:
            targets = ids_by_name.get(_canonical_name(dependency["name"]), [])
            wanted_version = dependency.get("version")
            wanted_source = dependency.get("source")
            if wanted_version:
                targets = [
                    target for target in targets if target["version"] == wanted_version
                ]
            if wanted_source:
                targets = [
                    target
                    for target in targets
                    if target.get("source") == wanted_source
                ]
            if not targets:
                raise ValueError(
                    f"Locked dependency target missing: {parent['name']} -> {dependency['name']}"
                )
            comments: list[str] = []
            if group:
                comments.append(f"uv group/extra: {group}")
            if dependency.get("marker"):
                comments.append(f"uv marker: {dependency['marker']}")
            for target in targets:
                relationship = {
                    "spdxElementId": _package_id(parent),
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": _package_id(target),
                }
                if comments:
                    relationship["comment"] = "; ".join(comments)
                relationships.append(relationship)

    for package in packages:
        add_dependencies(package, package.get("dependencies", []))
        if package is root:
            for extra, dependencies in package.get("optional-dependencies", {}).items():
                add_dependencies(package, dependencies, group=f"extra:{extra}")
            for group, dependencies in package.get("dev-dependencies", {}).items():
                add_dependencies(package, dependencies, group=f"dev:{group}")

    lock_digest = hashlib.sha256(lock_bytes).hexdigest()
    evidence_digest = hashlib.sha256(evidence_bytes).hexdigest()
    created_at = created or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    generator_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    namespace_digest = hashlib.sha256(
        f"{lock_digest}\0{evidence_digest}\0{generator_digest}\0{created_at}".encode(
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
            "created": created_at,
            "creators": ["Tool: scripts/generate_spdx_sbom.py"],
            "comment": (
                "Inventory of every package record in uv.lock, including platform marker "
                "variants, optional extras, and development dependencies. licenseDeclared "
                "uses valid SPDX expressions from exact locked artifact author metadata, "
                "license-file evidence tied to exact artifacts in uv.lock, or a reviewed "
                "version-specific legacy-value mapping recorded in "
                "docs/third-party-license-evidence.json; unresolved declarations and every "
                "licenseConcluded remain NOASSERTION pending review."
            ),
        },
        "packages": package_records,
        "relationships": relationships,
    }


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=root / "docs" / "third-party-license-evidence.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        required=True,
        help="existing offline cache containing files named by lowercase SHA-256, without extensions",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--created", help="Optional UTC SPDX timestamp, e.g. 2026-10-09T00:00:00Z"
    )
    args = parser.parse_args(argv)
    try:
        document = build_document(
            args.lockfile,
            artifact_cache_dir=args.cache_dir,
            created=args.created,
            license_evidence_path=args.evidence,
        )
    except (
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        print(
            f"SPDX SBOM generation failed: {escape_terminal_controls(str(exc))}",
            file=sys.stderr,
        )
        return 1
    try:
        output = write_atomic_text(
            args.output,
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        )
    except OSError as exc:
        print(
            f"SPDX SBOM writing failed: {escape_terminal_controls(str(exc))}",
            file=sys.stderr,
        )
        return 1
    output_label = escape_terminal_controls(str(output))
    print(
        f"Wrote {len(document['packages'])} packages and "
        f"{len(document['relationships'])} relationships to {output_label}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

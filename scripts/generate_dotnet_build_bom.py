from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from safe_output import write_atomic_text


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT / "native" / "windows" / "wfp-policy-plan"
PROJECT_FILE = PROJECT_ROOT / "WfpPolicyPlan.csproj"
LOCK_FILE = PROJECT_ROOT / "packages.lock.json"
GLOBAL_FILE = PROJECT_ROOT / "global.json"
CORE_ROOT = REPO_ROOT / "native" / "windows" / "wfp-policy-core"
CORE_PROJECT_FILE = CORE_ROOT / "WfpPolicy.Core.csproj"
CORE_GLOBAL_FILE = CORE_ROOT / "global.json"
RUNTIME_ROOT = REPO_ROOT / "native" / "windows" / "wfp-policy-runtime"
RUNTIME_PROJECT_FILE = RUNTIME_ROOT / "WfpPolicy.Runtime.csproj"
RUNTIME_LOCK_FILE = RUNTIME_ROOT / "packages.lock.json"
RUNTIME_GLOBAL_FILE = RUNTIME_ROOT / "global.json"
RUNTIME_TEST_ROOT = RUNTIME_ROOT / "tests"
RUNTIME_TEST_PROJECT_FILE = RUNTIME_TEST_ROOT / "WfpPolicy.Runtime.Harness.csproj"
RUNTIME_TEST_LOCK_FILE = RUNTIME_TEST_ROOT / "packages.lock.json"
CORE_LOCK_FILE = CORE_ROOT / "packages.lock.json"
NATIVE_READBACK_ROOT = REPO_ROOT / "native" / "windows" / "wfp-policy-native-readback"
NATIVE_READBACK_PROJECT_FILE = NATIVE_READBACK_ROOT / "WfpPolicy.NativeReadback.csproj"
NATIVE_READBACK_LOCK_FILE = NATIVE_READBACK_ROOT / "packages.lock.json"
NATIVE_READBACK_GLOBAL_FILE = NATIVE_READBACK_ROOT / "global.json"
NATIVE_READBACK_TEST_ROOT = NATIVE_READBACK_ROOT / "tests"
NATIVE_READBACK_TEST_PROJECT_FILE = (
    NATIVE_READBACK_TEST_ROOT / "WfpPolicy.NativeReadback.Harness.csproj"
)
NATIVE_READBACK_TEST_LOCK_FILE = NATIVE_READBACK_TEST_ROOT / "packages.lock.json"
NUGET_CONTENT_HASH_ROOT = REPO_ROOT / "scripts" / "nuget_content_hash"
NUGET_CONTENT_HASH_PROJECT_FILE = NUGET_CONTENT_HASH_ROOT / "NuGetContentHash.csproj"
NUGET_CONTENT_HASH_GLOBAL_FILE = NUGET_CONTENT_HASH_ROOT / "global.json"
BOM_SCHEMA_VERSION = "1.1"
MAX_EVIDENCE_FILE_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_GENERATED_FILES = 512
MAX_BUILD_OUTPUT_FILES = 32


class BomError(RuntimeError):
    pass


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_reparse_point(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _assert_no_reparse_components(path: Path, root: Path) -> bool:
    """Check lexical path components under root without following junctions."""
    absolute_root = Path(os.path.abspath(root))
    absolute_path = Path(os.path.abspath(path))
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise BomError("evidence path is outside its declared root") from exc

    current = absolute_root
    components = ((), *relative.parts)
    for index, component in enumerate(components):
        if component:
            current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise BomError(
                f"cannot inspect evidence path component {current.name}"
            ) from exc
        if _is_reparse_point(info):
            raise BomError(f"evidence path contains a reparse point: {current.name}")
        if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
            raise BomError(
                f"evidence path component is not a directory: {current.name}"
            )
    return True


def _safe_inventory_files(
    directory: Path,
    suffixes: set[str],
    *,
    recursive: bool,
    allow_missing: bool = False,
) -> list[Path]:
    """Inventory regular files while refusing symlink/junction traversal."""
    if not _assert_no_reparse_components(directory, REPO_ROOT):
        if allow_missing:
            return []
        raise BomError(f"evidence inventory directory is missing: {directory.name}")
    try:
        directory_info = directory.lstat()
    except OSError as exc:
        raise BomError(
            f"cannot inspect evidence inventory directory: {directory.name}"
        ) from exc
    if not stat.S_ISDIR(directory_info.st_mode):
        raise BomError(f"evidence inventory path is not a directory: {directory.name}")

    found: list[Path] = []
    pending = [directory]
    while pending:
        current = pending.pop()
        _assert_no_reparse_components(current, REPO_ROOT)
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        raise BomError(
                            f"cannot inspect evidence inventory entry: {entry.name}"
                        ) from exc
                    if _is_reparse_point(info):
                        raise BomError(
                            f"evidence inventory contains a reparse point: {entry.name}"
                        )
                    candidate = Path(entry.path)
                    if stat.S_ISDIR(info.st_mode):
                        if recursive:
                            pending.append(candidate)
                    elif (
                        stat.S_ISREG(info.st_mode)
                        and candidate.suffix.casefold() in suffixes
                    ):
                        found.append(candidate)
        except OSError as exc:
            raise BomError(
                f"cannot enumerate evidence inventory directory: {current.name}"
            ) from exc
    return found


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BomError(f"could not run {Path(command[0]).name}: {exc}") from exc
    if result.returncode != 0:
        detail = " ".join(result.stderr.split())[:600]
        raise BomError(
            f"command failed with exit code {result.returncode}: "
            f"{Path(command[0]).name} {command[1]} {detail}"
        )
    return result.stdout


def _sha256(path: Path, *, max_bytes: int = MAX_EVIDENCE_FILE_BYTES) -> tuple[str, int]:
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        _assert_no_reparse_components(path, REPO_ROOT)
    try:
        info = path.lstat()
    except OSError as exc:
        raise BomError(f"cannot inspect evidence file {path.name}: {exc}") from exc
    if not path.is_file() or path.is_symlink():
        raise BomError(f"evidence is not a regular non-symlink file: {path.name}")
    if info.st_size < 0 or info.st_size > max_bytes:
        raise BomError(f"evidence file exceeds the size limit: {path.name}")

    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise BomError(
                        f"evidence file grew past the size limit: {path.name}"
                    )
                digest.update(chunk)
    except OSError as exc:
        raise BomError(f"cannot read evidence file {path.name}: {exc}") from exc
    if total != info.st_size:
        raise BomError(f"evidence file changed while being hashed: {path.name}")
    return digest.hexdigest(), total


def _sha512_base64(path: Path, *, max_bytes: int = MAX_PACKAGE_BYTES) -> str:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BomError(f"cannot inspect evidence file {path.name}: {exc}") from exc
    if not path.is_file() or path.is_symlink():
        raise BomError(f"evidence is not a regular non-symlink file: {path.name}")
    if info.st_size < 0 or info.st_size > max_bytes:
        raise BomError(f"evidence file exceeds the size limit: {path.name}")

    digest = hashlib.sha512()
    total = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise BomError(
                        f"evidence file grew past the size limit: {path.name}"
                    )
                digest.update(chunk)
    except OSError as exc:
        raise BomError(f"cannot read evidence file {path.name}: {exc}") from exc
    if total != info.st_size:
        raise BomError(f"evidence file changed while being hashed: {path.name}")
    return base64.b64encode(digest.digest()).decode("ascii")


def _read_bounded(path: Path, *, max_bytes: int, encoding: str) -> str:
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        _assert_no_reparse_components(path, REPO_ROOT)
    try:
        info = path.lstat()
    except OSError as exc:
        raise BomError(f"cannot inspect evidence file {path.name}: {exc}") from exc
    if not path.is_file() or path.is_symlink():
        raise BomError(f"evidence is not a regular non-symlink file: {path.name}")
    if info.st_size < 0 or info.st_size > max_bytes:
        raise BomError(f"evidence file exceeds the size limit: {path.name}")
    try:
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except OSError as exc:
        raise BomError(f"cannot read evidence file {path.name}: {exc}") from exc
    if len(raw) > max_bytes or len(raw) != info.st_size:
        raise BomError(
            f"evidence file changed or grew past the size limit: {path.name}"
        )
    try:
        return raw.decode(encoding, errors="strict")
    except UnicodeError as exc:
        raise BomError(f"evidence file is not valid {encoding}: {path.name}") from exc


def _relative(path: Path, root: Path) -> str:
    try:
        return PurePosixPath(path.relative_to(root).as_posix()).as_posix()
    except ValueError as exc:
        raise BomError("evidence path is outside its declared root") from exc


def _file_record(
    path: Path, root: Path, *, max_bytes: int = MAX_EVIDENCE_FILE_BYTES
) -> dict[str, Any]:
    digest, size = _sha256(path, max_bytes=max_bytes)
    return {"path": _relative(path, root), "sizeBytes": size, "sha256": digest}


def _source_file_record(
    path: Path, root: Path, *, max_bytes: int = MAX_EVIDENCE_FILE_BYTES
) -> dict[str, Any]:
    """Hash source text with its repository-declared LF line endings."""
    content = _read_bounded(path, max_bytes=max_bytes, encoding="utf-8")
    canonical = content.replace("\r\n", "\n").encode("utf-8")
    return {
        "path": _relative(path, root),
        "sizeBytes": len(canonical),
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _global_packages_root(dotnet: str, project_root: Path) -> Path:
    output = _run(
        [dotnet, "nuget", "locals", "global-packages", "--list"], cwd=project_root
    )
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().casefold() == "global-packages":
            path = Path(value.strip()).expanduser().resolve()
            if path.is_dir():
                return path
    raise BomError("dotnet did not report an existing global packages directory")


def _build_nuget_content_hash_helper(dotnet: str) -> Path:
    try:
        global_json = json.loads(
            NUGET_CONTENT_HASH_GLOBAL_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BomError("could not read NuGet content-hash SDK pin") from exc
    expected_sdk = global_json.get("sdk", {}).get("version")
    sdk_version = _run([dotnet, "--version"], cwd=NUGET_CONTENT_HASH_ROOT).strip()
    if not isinstance(expected_sdk, str) or sdk_version != expected_sdk:
        raise BomError(
            f"NuGet content-hash helper requires SDK {expected_sdk!r}; got {sdk_version!r}"
        )

    _run(
        [
            dotnet,
            "build",
            str(NUGET_CONTENT_HASH_PROJECT_FILE),
            "--configuration",
            "Release",
            "--nologo",
            "--verbosity",
            "quiet",
            "-p:NuGetAudit=false",
        ],
        cwd=NUGET_CONTENT_HASH_ROOT,
    )
    helper_path = (
        NUGET_CONTENT_HASH_ROOT / "bin" / "Release" / "net10.0" / "NuGetContentHash.dll"
    )
    if not helper_path.is_file() or helper_path.is_symlink():
        raise BomError("NuGet content-hash helper output is missing or unsafe")
    return helper_path


def _nuget_content_hash(
    package_path: Path,
    dotnet: str,
    project_root: Path,
    helper_path: Path | None = None,
) -> str:
    if helper_path is None:
        helper_path = _build_nuget_content_hash_helper(dotnet)
    output = _run(
        [dotnet, str(helper_path), str(package_path)], cwd=project_root
    ).strip()
    try:
        digest = base64.b64decode(output, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BomError("NuGet content-hash helper returned malformed output") from exc
    if len(digest) != 64:
        raise BomError("NuGet content-hash helper returned a non-SHA-512 digest")
    return base64.b64encode(digest).decode("ascii")


def _source_inputs(project_root: Path, repo_root: Path) -> list[Path]:
    projects = [PROJECT_FILE, CORE_PROJECT_FILE]
    paths = [
        GLOBAL_FILE,
        LOCK_FILE,
        PROJECT_FILE,
        project_root / "NativeMethods.txt",
        CORE_GLOBAL_FILE,
        CORE_PROJECT_FILE,
        CORE_LOCK_FILE,
    ]
    paths.extend(_safe_inventory_files(project_root, {".cs"}, recursive=False))
    paths.extend(_safe_inventory_files(CORE_ROOT, {".cs"}, recursive=False))

    for project_file in projects:
        try:
            document = ET.parse(project_file)
        except (OSError, ET.ParseError) as exc:
            raise BomError("could not parse WFP project file") from exc
        project_dir = project_file.parent
        for node in document.findall(".//{*}Compile"):
            include = node.get("Include")
            if not include:
                continue
            # Globs are rejected to keep the recorded source closure deterministic.
            if any(character in include for character in "*?[]"):
                raise BomError("wildcard Compile Include needs explicit BOM support")
            source = (project_dir / include.replace("\\", "/")).resolve()
            if not source.is_file() or source.is_symlink():
                raise BomError(
                    "explicit project source is missing or not a regular file"
                )
            paths.append(source)
        for node in document.findall(".//{*}ProjectReference"):
            include = node.get("Include")
            if not include or any(character in include for character in "*?[]"):
                raise BomError("project reference is missing or uses a wildcard")
            referenced_project = (project_dir / include.replace("\\", "/")).resolve()
            if not referenced_project.is_file() or referenced_project.is_symlink():
                raise BomError("project reference is missing or not a regular file")
            paths.append(referenced_project)

    unique = {path.resolve() for path in paths}
    for path in unique:
        if path not in {
            GLOBAL_FILE.resolve(),
            LOCK_FILE.resolve(),
            PROJECT_FILE.resolve(),
            CORE_LOCK_FILE.resolve(),
        }:
            try:
                path.relative_to(repo_root)
            except ValueError as exc:
                raise BomError("project source escapes the repository root") from exc
    return sorted(unique, key=lambda path: _relative(path, repo_root).casefold())


def _runtime_source_inputs(repo_root: Path) -> list[Path]:
    fixed_inputs = [
        RUNTIME_GLOBAL_FILE,
        RUNTIME_PROJECT_FILE,
        RUNTIME_LOCK_FILE,
        RUNTIME_ROOT / "AssemblyInfo.cs",
        RUNTIME_ROOT / "BaselineCoordinator.cs",
        RUNTIME_TEST_PROJECT_FILE,
        RUNTIME_TEST_LOCK_FILE,
        RUNTIME_TEST_ROOT / "Program.cs",
        CORE_GLOBAL_FILE,
        CORE_PROJECT_FILE,
        CORE_LOCK_FILE,
        CORE_ROOT / "AssemblyInfo.cs",
        CORE_ROOT / "LeasePolicyCompiler.cs",
        NATIVE_READBACK_GLOBAL_FILE,
        NATIVE_READBACK_PROJECT_FILE,
        NATIVE_READBACK_LOCK_FILE,
        NATIVE_READBACK_ROOT / "AssemblyInfo.cs",
        NATIVE_READBACK_ROOT / "NativeMethods.txt",
    ]
    roots = [RUNTIME_ROOT, RUNTIME_TEST_ROOT, CORE_ROOT, NATIVE_READBACK_ROOT]
    source_files = [
        path
        for root in roots
        for path in _safe_inventory_files(root, {".cs"}, recursive=True)
        if not (
            root == NATIVE_READBACK_ROOT and NATIVE_READBACK_TEST_ROOT in path.parents
        )
        and not any(part.casefold() in {"bin", "obj"} for part in path.parts)
    ]
    paths = fixed_inputs + source_files
    for path in paths:
        resolved = path.resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            raise BomError("runtime source input escapes the repository root") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise BomError("runtime source input is missing or not a regular file")
    return sorted(
        {path.resolve() for path in paths},
        key=lambda path: _relative(path, repo_root).casefold(),
    )


def _native_readback_source_inputs(repo_root: Path) -> list[Path]:
    fixed_inputs = [
        NATIVE_READBACK_GLOBAL_FILE,
        NATIVE_READBACK_PROJECT_FILE,
        NATIVE_READBACK_ROOT / "NativeMethods.txt",
        NATIVE_READBACK_LOCK_FILE,
        NATIVE_READBACK_ROOT / "AssemblyInfo.cs",
        NATIVE_READBACK_TEST_PROJECT_FILE,
        NATIVE_READBACK_TEST_LOCK_FILE,
        NATIVE_READBACK_TEST_ROOT / "Program.cs",
    ]
    roots = [NATIVE_READBACK_ROOT, NATIVE_READBACK_TEST_ROOT]
    source_files = [
        path
        for root in roots
        for path in _safe_inventory_files(root, {".cs"}, recursive=True)
        if not any(part.casefold() in {"bin", "obj"} for part in path.parts)
    ]
    paths = fixed_inputs + source_files
    for path in paths:
        resolved = path.resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            raise BomError(
                "native readback source input escapes the repository root"
            ) from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise BomError(
                "native readback source input is missing or not a regular file"
            )
    return sorted(
        {path.resolve() for path in paths},
        key=lambda path: _relative(path, repo_root).casefold(),
    )


def _native_readback_locked_packages(
    lock: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    dependencies = lock.get("dependencies", {}).get("net10.0-windows7.0")
    if not isinstance(dependencies, dict) or not dependencies:
        raise BomError(
            "native readback lockfile has no net10.0-windows7.0 dependency graph"
        )
    result: list[tuple[str, str, dict[str, Any]]] = []
    for package_id, record in dependencies.items():
        if not isinstance(record, dict):
            raise BomError("native readback lockfile package record is malformed")
        if record.get("type") == "Project":
            raise BomError("native readback library unexpectedly depends on a project")
        version = record.get("resolved")
        content_hash = record.get("contentHash")
        if not isinstance(version, str) or not isinstance(content_hash, str):
            raise BomError(
                "native readback lockfile package lacks a resolved version or content hash"
            )
        result.append((package_id, version, record))
    return sorted(result, key=lambda item: item[0].casefold())


def _native_readback_build_record(
    dotnet: str,
    sdk_version: str,
    main_packages: list[dict[str, Any]],
    *,
    run_build: bool,
) -> dict[str, Any]:
    try:
        global_json = json.loads(
            _read_bounded(
                NATIVE_READBACK_GLOBAL_FILE, max_bytes=64 * 1024, encoding="utf-8"
            )
        )
        lock = json.loads(
            _read_bounded(
                NATIVE_READBACK_LOCK_FILE, max_bytes=4 * 1024 * 1024, encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise BomError(
            "native readback SDK or NuGet lock metadata is malformed"
        ) from exc
    native_sdk = (
        global_json.get("sdk", {}).get("version")
        if isinstance(global_json, dict)
        else None
    )
    if native_sdk != sdk_version:
        raise BomError("native readback SDK pin does not match the BOM toolchain")

    locked_packages = _native_readback_locked_packages(lock)
    expected_packages = [
        (package["id"], package["version"], package["lockContentHash"])
        for package in main_packages
    ]
    actual_packages = [
        (package_id, version, record["contentHash"])
        for package_id, version, record in locked_packages
    ]
    if actual_packages != expected_packages:
        raise BomError(
            "native readback package graph differs from the top-level pinned WFP package graph"
        )
    test_lock = json.loads(
        _read_bounded(
            NATIVE_READBACK_TEST_LOCK_FILE, max_bytes=4 * 1024 * 1024, encoding="utf-8"
        )
    )
    if not isinstance(test_lock, dict) or test_lock.get("version") != 1:
        raise BomError("native readback harness lockfile has an unsupported shape")
    for target in test_lock.get("dependencies", {}).values():
        if not isinstance(target, dict) or any(
            not isinstance(record, dict) or record.get("type") != "Project"
            for record in target.values()
        ):
            raise BomError(
                "native readback harness lockfile must contain only project references"
            )

    build_command = [
        dotnet,
        "build",
        str(NATIVE_READBACK_TEST_PROJECT_FILE),
        "--configuration",
        "Release",
        "--no-restore",
        "-p:Platform=x64",
        "--nologo",
        "--verbosity",
        "quiet",
    ]
    if run_build:
        _run(
            [
                dotnet,
                "restore",
                str(NATIVE_READBACK_TEST_PROJECT_FILE),
                "--locked-mode",
                "-p:NuGetAudit=false",
            ],
            cwd=NATIVE_READBACK_ROOT,
        )
        _run(build_command, cwd=NATIVE_READBACK_ROOT)

    output_roots = [
        NATIVE_READBACK_ROOT
        / "bin"
        / "x64"
        / "Release"
        / "net10.0-windows"
        / "win-x64",
        NATIVE_READBACK_TEST_ROOT
        / "bin"
        / "x64"
        / "Release"
        / "net10.0-windows"
        / "win-x64",
    ]
    output_files = sorted(
        (
            path
            for output_root in output_roots
            for path in _safe_inventory_files(
                output_root,
                {".dll", ".exe", ".pdb", ".json"},
                recursive=False,
                allow_missing=True,
            )
        ),
        key=lambda path: _relative(path, REPO_ROOT).casefold(),
    )
    if not output_files or len(output_files) > MAX_BUILD_OUTPUT_FILES:
        raise BomError(
            "native readback Release output inventory is empty or exceeds its limit"
        )

    generated_root = (
        NATIVE_READBACK_ROOT
        / "obj"
        / "x64"
        / "Release"
        / "net10.0-windows"
        / "win-x64"
        / "generated"
    )
    generated_files = sorted(
        _safe_inventory_files(
            generated_root, {".cs"}, recursive=True, allow_missing=True
        ),
        key=lambda path: _relative(path, REPO_ROOT).casefold(),
    )
    if not generated_files or len(generated_files) > MAX_GENERATED_FILES:
        raise BomError(
            "native readback generated source inventory is empty or exceeds its limit"
        )

    return {
        "projects": [
            _relative(NATIVE_READBACK_PROJECT_FILE, REPO_ROOT),
            _relative(NATIVE_READBACK_TEST_PROJECT_FILE, REPO_ROOT),
        ],
        "targetFramework": "net10.0-windows",
        "runtimeIdentifier": "win-x64",
        "purpose": "read-only native BFE/WFP snapshot prototype and unmanaged fake-API fixture harness; not connected to policy activation",
        "globalJson": _file_record(NATIVE_READBACK_GLOBAL_FILE, REPO_ROOT),
        "sourceInputs": [
            _source_file_record(path, REPO_ROOT)
            for path in _native_readback_source_inputs(REPO_ROOT)
        ],
        "nugetLocks": [
            _source_file_record(path, REPO_ROOT)
            for path in (NATIVE_READBACK_LOCK_FILE, NATIVE_READBACK_TEST_LOCK_FILE)
        ],
        "nugetPackages": [
            {
                "id": package_id,
                "version": version,
                "lockContentHash": record["contentHash"],
            }
            for package_id, version, record in locked_packages
        ],
        "buildCommand": "dotnet restore <native readback harness> --locked-mode -p:NuGetAudit=false; dotnet build <native readback harness> --configuration Release --no-restore -p:Platform=x64 --nologo --verbosity quiet",
        "harnessCommand": "dotnet run --project <native readback harness> --configuration Release -p:Platform=x64 --no-build --no-restore",
        "generatedSources": [_file_record(path, REPO_ROOT) for path in generated_files],
        "buildOutputs": [_file_record(path, REPO_ROOT) for path in output_files],
        "limitations": [
            "fixture harness uses an in-memory fake API and does not call BFE/WFP or prove a live native snapshot",
            "snapshots remain incomplete because object ACL policy comparison and read-ACL enumeration coverage are unproven; IPsec provider-context payloads remain unnormalized",
            "does not prove policy equivalence, enforcement, CaptureService integration, or readiness-gate behavior",
        ],
    }


def _validate_project_only_lock(path: Path) -> None:
    try:
        lock = json.loads(
            _read_bounded(path, max_bytes=4 * 1024 * 1024, encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise BomError("runtime NuGet lockfile is malformed") from exc
    if not isinstance(lock, dict) or lock.get("version") != 1:
        raise BomError("runtime NuGet lockfile has an unsupported shape")
    dependencies = lock.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        raise BomError("runtime NuGet lockfile has no dependency targets")
    for target in dependencies.values():
        if not isinstance(target, dict):
            raise BomError("runtime NuGet lockfile target is malformed")
        for package_id, record in target.items():
            if not isinstance(package_id, str) or not isinstance(record, dict):
                raise BomError("runtime NuGet lockfile record is malformed")
            if record.get("type") != "Project":
                raise BomError(
                    "runtime acquired a NuGet package; extend build BOM package inventory"
                )
            if set(record) - {"type", "dependencies"}:
                raise BomError("runtime project dependency record has unexpected data")
            project_dependencies = record.get("dependencies", {})
            if not isinstance(project_dependencies, dict) or not all(
                isinstance(name, str) and isinstance(constraint, str)
                for name, constraint in project_dependencies.items()
            ):
                raise BomError("runtime project dependency list is malformed")


def _runtime_build_record(
    dotnet: str, sdk_version: str, *, run_build: bool
) -> dict[str, Any]:
    try:
        global_json = json.loads(
            _read_bounded(RUNTIME_GLOBAL_FILE, max_bytes=64 * 1024, encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise BomError("runtime SDK metadata is malformed") from exc
    runtime_sdk = (
        global_json.get("sdk", {}).get("version")
        if isinstance(global_json, dict)
        else None
    )
    if runtime_sdk != sdk_version:
        raise BomError("runtime project SDK pin does not match the BOM toolchain")

    for lock_path in (RUNTIME_LOCK_FILE, RUNTIME_TEST_LOCK_FILE, CORE_LOCK_FILE):
        _validate_project_only_lock(lock_path)

    if run_build:
        _run(
            [
                dotnet,
                "restore",
                str(RUNTIME_TEST_PROJECT_FILE),
                "--locked-mode",
                "-p:NuGetAudit=false",
            ],
            cwd=RUNTIME_ROOT,
        )
        _run(
            [
                dotnet,
                "build",
                str(RUNTIME_TEST_PROJECT_FILE),
                "--configuration",
                "Release",
                "--no-restore",
                "-p:Platform=x64",
                "--nologo",
                "--verbosity",
                "quiet",
            ],
            cwd=RUNTIME_ROOT,
        )

    output_roots = [
        CORE_ROOT / "bin" / "x64" / "Release" / "net10.0",
        RUNTIME_ROOT / "bin" / "x64" / "Release" / "net10.0-windows",
        RUNTIME_TEST_ROOT / "bin" / "x64" / "Release" / "net10.0-windows" / "win-x64",
        NATIVE_READBACK_ROOT
        / "bin"
        / "x64"
        / "Release"
        / "net10.0-windows"
        / "win-x64",
    ]
    output_files = sorted(
        (
            path
            for output_root in output_roots
            for path in _safe_inventory_files(
                output_root,
                {".dll", ".exe", ".pdb", ".json"},
                recursive=False,
            )
        ),
        key=lambda path: _relative(path, REPO_ROOT).casefold(),
    )
    if not output_files or len(output_files) > MAX_BUILD_OUTPUT_FILES:
        raise BomError("runtime Release output inventory is empty or exceeds its limit")

    generated_root = (
        RUNTIME_ROOT / "obj" / "x64" / "Release" / "net10.0-windows" / "generated"
    )
    generated_files = sorted(
        _safe_inventory_files(
            generated_root, {".cs"}, recursive=True, allow_missing=True
        ),
        key=lambda path: _relative(path, REPO_ROOT).casefold(),
    )
    if len(generated_files) > MAX_GENERATED_FILES:
        raise BomError("runtime generated source inventory exceeds its limit")

    return {
        "projects": [
            _relative(RUNTIME_PROJECT_FILE, REPO_ROOT),
            _relative(RUNTIME_TEST_PROJECT_FILE, REPO_ROOT),
            _relative(NATIVE_READBACK_PROJECT_FILE, REPO_ROOT),
        ],
        "targetFramework": "net10.0-windows",
        "runtimeIdentifier": "win-x64",
        "purpose": "source-only persistent WFP baseline coordinator, strict native readback adapter, and fake-store harness; no native WFP mutation store",
        "globalJson": _file_record(RUNTIME_GLOBAL_FILE, REPO_ROOT),
        "sourceInputs": [
            _source_file_record(path, REPO_ROOT)
            for path in _runtime_source_inputs(REPO_ROOT)
        ],
        "nugetLocks": [
            _source_file_record(path, REPO_ROOT)
            for path in (
                RUNTIME_LOCK_FILE,
                RUNTIME_TEST_LOCK_FILE,
                CORE_LOCK_FILE,
                NATIVE_READBACK_LOCK_FILE,
            )
        ],
        "nugetPackages": [],
        "buildCommand": "dotnet restore <runtime harness> --locked-mode; dotnet build <runtime harness> --configuration Release --no-restore -p:Platform=x64 --nologo --verbosity quiet",
        "generatedSources": [_file_record(path, REPO_ROOT) for path in generated_files],
        "buildOutputs": [_file_record(path, REPO_ROOT) for path in output_files],
        "limitations": [
            "does not include a native BFE/WFP store or prove that filters were applied",
            "the native readback adapter rejects the current incomplete reader snapshot before mutation and is not connected to the default store or CaptureService",
            "does not prove CaptureService integration, process isolation, or deployed service behavior",
        ],
    }


def _lock_packages(lock: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    dependencies = lock.get("dependencies", {}).get("net10.0")
    if not isinstance(dependencies, dict) or not dependencies:
        raise BomError("lockfile has no net10.0 dependency graph")
    result: list[tuple[str, str, dict[str, Any]]] = []
    for package_id, record in dependencies.items():
        if not isinstance(record, dict):
            raise BomError("lockfile package record is malformed")
        if record.get("type") == "Project":
            if set(record) != {"type"}:
                raise BomError("project dependency record has unexpected package data")
            continue
        version = record.get("resolved")
        content_hash = record.get("contentHash")
        if not isinstance(version, str) or not isinstance(content_hash, str):
            raise BomError(
                "lockfile package is missing a resolved version or content hash"
            )
        result.append((package_id, version, record))
    return sorted(result, key=lambda item: item[0].casefold())


def _package_record(
    package_root: Path,
    package_id: str,
    version: str,
    lock_record: dict[str, Any],
    dotnet: str,
    project_root: Path,
    helper_path: Path | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", package_id) or not re.fullmatch(
        r"[A-Za-z0-9_.+-]+", version
    ):
        raise BomError("unsafe NuGet package identity in lockfile")
    package_dir = package_root / package_id.casefold() / version.casefold()
    package_path = package_dir / f"{package_id}.{version}.nupkg"
    metadata_path = package_dir / ".nupkg.metadata"
    sha512_path = package_dir / f"{package_id}.{version}.nupkg.sha512"
    signature_path = package_dir / ".signature.p7s"

    package_sha256, package_size = _sha256(package_path, max_bytes=MAX_PACKAGE_BYTES)
    sha512_expected = _read_bounded(
        sha512_path, max_bytes=256, encoding="ascii"
    ).strip()
    sha512_actual = _sha512_base64(package_path)
    if sha512_actual != sha512_expected:
        raise BomError(f"NuGet archive SHA-512 sidecar mismatch for {package_id}")
    try:
        metadata = json.loads(
            _read_bounded(metadata_path, max_bytes=64 * 1024, encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise BomError(f"NuGet metadata is malformed for {package_id}") from exc
    if not isinstance(metadata, dict):
        raise BomError(f"NuGet metadata is malformed for {package_id}")
    lock_hash = lock_record["contentHash"]
    if metadata.get("contentHash") != lock_hash:
        raise BomError(f"NuGet metadata contentHash mismatch for {package_id}")
    content_hash_actual = _nuget_content_hash(
        package_path, dotnet, project_root, helper_path
    )
    if content_hash_actual != lock_hash:
        raise BomError(
            f"NuGet archive does not match lock contentHash for {package_id}"
        )
    dependencies = lock_record.get("dependencies", {})
    if not isinstance(dependencies, dict) or not all(
        isinstance(name, str) and isinstance(constraint, str)
        for name, constraint in dependencies.items()
    ):
        raise BomError(f"lockfile dependency list is malformed for {package_id}")
    signature_sha256, signature_size = _sha256(
        signature_path, max_bytes=MAX_PACKAGE_BYTES
    )

    # NuGet verification is run for every exact package archive. The BOM stores
    # status and command, not locale-sensitive console output or user paths.
    _run([dotnet, "nuget", "verify", "--all", str(package_path)], cwd=project_root)
    return {
        "id": package_id,
        "version": version,
        "dependencyType": lock_record.get("type", "Transitive"),
        "lockContentHash": lock_hash,
        "nupkg": {
            "path": _relative(package_path, package_root),
            "sizeBytes": package_size,
            "sha256": package_sha256,
            "sha512Base64": sha512_actual,
            "lockContentHashMatchesNuGetMetadata": True,
            "lockContentHashMatchesNuGetComputedContentHash": True,
            "signatureFile": {
                "path": _relative(signature_path, package_root),
                "sizeBytes": signature_size,
                "sha256": signature_sha256,
            },
            "nugetVerifyAll": {
                "status": "passed",
                "command": "dotnet nuget verify --all <nupkg>",
            },
        },
        "dependencies": dict(sorted(dependencies.items())),
    }


def create_bom(dotnet: str, *, run_build: bool = True) -> dict[str, Any]:
    try:
        global_json = json.loads(GLOBAL_FILE.read_text(encoding="utf-8"))
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BomError("could not read SDK and NuGet lock metadata") from exc
    expected_sdk = global_json.get("sdk", {}).get("version")
    if not isinstance(expected_sdk, str):
        raise BomError("global.json does not pin an SDK version")
    sdk_version = _run([dotnet, "--version"], cwd=PROJECT_ROOT).strip()
    if sdk_version != expected_sdk:
        raise BomError(
            f"resolved .NET SDK {sdk_version!r} does not match {expected_sdk!r}"
        )

    build_command = [
        dotnet,
        "build",
        str(PROJECT_FILE),
        "--configuration",
        "Release",
        "--runtime",
        "win-x64",
        "--no-restore",
        "--nologo",
        "--verbosity",
        "quiet",
    ]
    if run_build:
        _run(build_command, cwd=PROJECT_ROOT)

    output_root = PROJECT_ROOT / "bin" / "Release" / "net10.0" / "win-x64"
    generated_root = (
        PROJECT_ROOT / "obj" / "Release" / "net10.0" / "win-x64" / "generated"
    )
    generated_files = sorted(
        _safe_inventory_files(generated_root, {".cs"}, recursive=True),
        key=lambda path: _relative(path, PROJECT_ROOT).casefold(),
    )
    if not generated_files or len(generated_files) > MAX_GENERATED_FILES:
        raise BomError(
            "generated source inventory is empty or exceeds its file-count limit"
        )
    output_files = sorted(
        _safe_inventory_files(
            output_root, {".dll", ".exe", ".pdb", ".json"}, recursive=False
        ),
        key=lambda path: _relative(path, PROJECT_ROOT).casefold(),
    )
    if not output_files or len(output_files) > MAX_BUILD_OUTPUT_FILES:
        raise BomError(
            "Release output inventory is empty or exceeds its file-count limit"
        )

    package_root = _global_packages_root(dotnet, PROJECT_ROOT)
    helper_path = _build_nuget_content_hash_helper(dotnet)
    packages = [
        _package_record(
            package_root,
            package_id,
            version,
            record,
            dotnet,
            PROJECT_ROOT,
            helper_path,
        )
        for package_id, version, record in _lock_packages(lock)
    ]
    source_inputs = _source_inputs(PROJECT_ROOT, REPO_ROOT)
    runtime_build = _runtime_build_record(dotnet, sdk_version, run_build=run_build)
    native_readback_build = _native_readback_build_record(
        dotnet, sdk_version, packages, run_build=run_build
    )
    target_lock = lock.get("dependencies", {}).get("net10.0/win-x64", {})
    if target_lock:
        raise BomError("runtime-specific lock target contains unaccounted packages")

    return {
        "bomFormat": "douyin-transcript-dotnet-build-bom",
        "schemaVersion": BOM_SCHEMA_VERSION,
        "scope": {
            "project": "native/windows/wfp-policy-plan",
            "targetFramework": "net10.0",
            "runtimeIdentifier": "win-x64",
            "purpose": "build-time WFP policy-plan prototype; not application runtime SBOM",
            "limitations": [
                "does not determine license applicability or redistribution obligations",
                "does not prove runtime linking or deployed service behavior",
                "does not prove that generated WFP filters were applied",
            ],
        },
        "toolchain": {
            "sdkVersion": sdk_version,
            "globalJson": _file_record(GLOBAL_FILE, REPO_ROOT),
            "buildCommand": "dotnet build <project> --configuration Release --runtime win-x64 --no-restore --nologo --verbosity quiet",
            "packageSignatureCommand": "dotnet nuget verify --all <nupkg>",
        },
        "sourceInputs": [
            _source_file_record(path, REPO_ROOT) for path in source_inputs
        ],
        "nugetLock": _source_file_record(LOCK_FILE, REPO_ROOT),
        "packages": packages,
        "generatedSources": [
            _file_record(path, PROJECT_ROOT) for path in generated_files
        ],
        "buildOutputs": [_file_record(path, PROJECT_ROOT) for path in output_files],
        "relatedBuilds": [runtime_build, native_readback_build],
    }


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return write_atomic_text(path, encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the pinned Windows WFP project and write its separate build BOM."
    )
    parser.add_argument(
        "--dotnet", required=True, help="path to the pinned dotnet host"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "dotnet-windows-build-bom.json",
        help="output path (defaults to docs/dotnet-windows-build-bom.json)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="skip the WFP project build; the NuGet content-hash helper is still compiled",
    )
    args = parser.parse_args(argv)
    try:
        dotnet = str(Path(args.dotnet).resolve(strict=True))
        if not Path(dotnet).is_file() or Path(dotnet).is_symlink():
            raise BomError("dotnet must be a regular executable file")
        bom = create_bom(dotnet, run_build=not args.skip_build)
        output = _write_json(args.output, bom)
    except (BomError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"dotnet build BOM failed: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(bom['packages'])} package records to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Local model profiles and read-only Hugging Face cache discovery.

This module deliberately does not download model files.  Setup code can use
``model_spec`` to select the repository and ``resolve_model_path`` to reuse a
complete local copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    profile: str
    size: str
    repository: str
    revision: str
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1

    @property
    def model_name(self) -> str:
        return f"faster-whisper-{self.size}-int8"


_PROFILES = {
    # Pin the upstream Hugging Face commit so setup never resolves mutable `main`.
    # Provenance links and the selection date are recorded in references/MODEL_PROVENANCE.md.
    "balanced": ModelSpec(
        "balanced",
        "medium",
        "Systran/faster-whisper-medium",
        "08e178d48790749d25932bbc082711ddcfdfbc4f",
    ),
    "medium": ModelSpec(
        "balanced",
        "medium",
        "Systran/faster-whisper-medium",
        "08e178d48790749d25932bbc082711ddcfdfbc4f",
    ),
    "fast": ModelSpec(
        "fast",
        "small",
        "Systran/faster-whisper-small",
        "536b0662742c02347bc0e980a01041f333bce120",
    ),
    "small": ModelSpec(
        "fast",
        "small",
        "Systran/faster-whisper-small",
        "536b0662742c02347bc0e980a01041f333bce120",
    ),
}
_REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")
_PROVENANCE_FILE = ".douyin-transcript-model.json"
_PROVENANCE_SCHEMA_VERSION = 1


def model_spec(profile: str = "balanced") -> ModelSpec:
    """Return the fixed CPU/int8 specification for a supported profile."""
    try:
        return _PROFILES[profile.casefold()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"unsupported model profile: {profile!r}") from exc


def is_complete_model(path: Path) -> bool:
    """Check that a model directory has the files needed for local inference.

    Checking file size and parsing ``config.json`` rejects empty or obviously
    partial Hugging Face snapshots.  Opening the native model is intentionally
    outside this offline filesystem check.
    """
    try:
        if not path.is_dir():
            return False
        for name in _REQUIRED_FILES:
            file_path = path / name
            if not file_path.is_file() or file_path.stat().st_size <= 0:
                return False
        with (path / "config.json").open("r", encoding="utf-8") as stream:
            config = json.load(stream)
        return isinstance(config, dict) and bool(config)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False


def _default_hub_cache() -> Path:
    configured_home = os.environ.get("HF_HOME")
    if configured_home:
        return Path(configured_home).expanduser() / "hub"
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "huggingface" / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    """Return the Git object hash used as ETag for ordinary Hub files."""
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cache_component_is_trusted(info: os.stat_result, *, is_directory: bool) -> bool:
    """Check POSIX ownership and write access for one Hub cache component.

    Read access for other users does not let them replace a model. Root-owned
    system directories and a sticky shared temporary directory are safe
    ancestors; writable non-sticky directories are not.
    """
    if os.name == "nt":
        return True
    trusted_owners = {os.geteuid(), 0}
    if info.st_uid not in trusted_owners:
        return False
    mode = stat.S_IMODE(info.st_mode)
    if is_directory:
        if not stat.S_ISDIR(info.st_mode):
            return False
        if mode & 0o022 and not (mode & stat.S_ISVTX):
            return False
    else:
        if not stat.S_ISREG(info.st_mode) or mode & 0o022:
            return False
    return True


def _cache_path_is_trusted(path: Path, *, is_directory: bool = True) -> bool:
    """Reject cache paths whose owner or writable ancestors permit substitution."""
    candidate = Path(path).expanduser()
    if any(part == ".." for part in candidate.parts):
        return False
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))

    if os.name == "nt":
        components = [Path(candidate.anchor)]
        current = Path(candidate.anchor)
        for name in candidate.parts[1:]:
            current = current / name
            components.append(current)
        for component in components:
            try:
                info = component.lstat()
            except OSError:
                return False
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        # Windows ACL inspection also rejects reparse points and checks all
        # ancestors. The API intentionally fails closed when access is unknown.
        from .storage_security import inspect_private_path

        return inspect_private_path(candidate).status == "private"

    components = [Path(candidate.anchor)]
    current = Path(candidate.anchor)
    for name in candidate.parts[1:]:
        current = current / name
        components.append(current)
    for index, component in enumerate(components):
        try:
            info = component.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return False
        final_component = index == len(components) - 1
        if not _cache_component_is_trusted(
            info, is_directory=True if not final_component else is_directory
        ):
            return False
    return True


def _hub_blob_name_matches_content(path: Path) -> bool:
    """Verify a Hub blob against its content-addressed filename."""
    name = path.name.casefold()
    try:
        if len(name) == 64 and all(character in "0123456789abcdef" for character in name):
            return _sha256_file(path) == name
        if len(name) == 40 and all(character in "0123456789abcdef" for character in name):
            return _git_blob_sha1(path) == name
    except OSError:
        return False
    return False


def _is_verified_hub_snapshot(path: Path, spec: ModelSpec) -> bool:
    """Validate a pinned Hub snapshot's trust chain and any blob ETags."""
    candidate = Path(path).expanduser()
    if any(part == ".." for part in candidate.parts):
        return False
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))
    repo_cache_name = "models--" + spec.repository.replace("/", "--")
    if (
        candidate.name != spec.revision
        or candidate.parent.name != "snapshots"
        or candidate.parent.parent.name != repo_cache_name
    ):
        return False
    if not _cache_path_is_trusted(candidate, is_directory=True):
        return False
    try:
        resolved = candidate.resolve(strict=True)
        blobs_dir = candidate.parent.parent / "blobs"
    except OSError:
        return False
    resolved_matches = os.path.normcase(str(resolved)) == os.path.normcase(str(candidate))
    if not resolved_matches:
        return False
    blobs_resolved = None
    if blobs_dir.exists():
        try:
            blobs_resolved = blobs_dir.resolve(strict=True)
        except OSError:
            return False
        if not _cache_path_is_trusted(blobs_dir, is_directory=True):
            return False
    if not is_complete_model(candidate):
        return False

    for name in _REQUIRED_FILES:
        entry = candidate / name
        try:
            info = entry.lstat()
        except OSError:
            return False
        if getattr(info, "st_file_attributes", 0) & 0x400:
            # Windows reparse points other than ordinary symlinks are not part
            # of the Hub snapshot format supported by this resolver.
            if not stat.S_ISLNK(info.st_mode):
                return False
        if stat.S_ISLNK(info.st_mode):
            if blobs_resolved is None:
                return False
            try:
                blob = entry.resolve(strict=True)
            except OSError:
                return False
            if blob.parent != blobs_resolved or not _cache_path_is_trusted(
                blob, is_directory=False
            ):
                return False
            if not _hub_blob_name_matches_content(blob):
                return False
        elif not _cache_path_is_trusted(entry, is_directory=False):
            # Windows may store regular copies when symlinks are unavailable.
            # The trusted owner/ancestor chain prevents another account from
            # replacing them; unlike blob links, these copies have no ETag to
            # compare locally.
            return False
    return True


def write_model_provenance(path: Path, spec: ModelSpec) -> Path:
    """Record the pinned source and content digests after a successful setup download.

    The manifest is stored beside the app-local model.  Runtime resolution checks
    both the configured Hugging Face repository/revision and every required file
    digest, so an unmarked or later-modified local model is never selected.
    """
    model_path = Path(path)
    if not is_complete_model(model_path):
        raise ValueError(f"cannot record provenance for an incomplete model: {model_path}")

    payload = {
        "schema_version": _PROVENANCE_SCHEMA_VERSION,
        "source": "huggingface_hub.snapshot_download",
        "repository": spec.repository,
        "revision": spec.revision,
        "files": {name: _sha256_file(model_path / name) for name in _REQUIRED_FILES},
    }
    destination = model_path / _PROVENANCE_FILE
    temporary = model_path / f"{_PROVENANCE_FILE}.tmp-{secrets.token_hex(8)}"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return destination


def _has_valid_local_provenance(path: Path, spec: ModelSpec) -> bool:
    manifest = path / _PROVENANCE_FILE
    try:
        manifest.lstat()
        if not manifest.is_file() or manifest.is_symlink():
            return False
        with manifest.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            return False
        if (
            payload.get("schema_version") != _PROVENANCE_SCHEMA_VERSION
            or payload.get("source") != "huggingface_hub.snapshot_download"
            or payload.get("repository") != spec.repository
            or payload.get("revision") != spec.revision
        ):
            return False
        files = payload.get("files")
        if not isinstance(files, dict) or set(files) != set(_REQUIRED_FILES):
            return False
        if any(
            not isinstance(files[name], str) or len(files[name]) != 64 for name in _REQUIRED_FILES
        ):
            return False
        return all(_sha256_file(path / name) == files[name] for name in _REQUIRED_FILES)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return False


def is_compatible_model_path(path: Path, spec: ModelSpec) -> bool:
    """Check completeness and pinned provenance for a model directory."""
    candidate = Path(path).expanduser()
    repo_cache_name = "models--" + spec.repository.replace("/", "--")
    if (
        candidate.name == spec.revision
        and candidate.parent.name == "snapshots"
        and candidate.parent.parent.name == repo_cache_name
    ):
        return _is_verified_hub_snapshot(candidate, spec)
    if not is_complete_model(candidate):
        return False
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return _has_valid_local_provenance(resolved, spec)


def _hub_cache_roots(data_dir: Path) -> tuple[Path, ...]:
    # faster-whisper's ``download_root`` stores Hub repositories beneath this
    # directory, which is also the app's preferred model cache.
    roots: list[Path] = [Path(data_dir).expanduser() / "models"]
    hub_override = os.environ.get("HF_HUB_CACHE")
    if hub_override:
        roots.append(Path(hub_override).expanduser())
    home_override = os.environ.get("HF_HOME")
    if home_override:
        roots.append(Path(home_override).expanduser() / "hub")
    roots.append(_default_hub_cache())
    # Keep order while avoiding duplicate paths that differ only by relative form.
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(os.path.abspath(root))
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return tuple(unique)


def _valid_snapshot(repo_cache: Path, spec: ModelSpec) -> Path | None:
    """Return only the complete snapshot whose directory is the pinned revision."""
    candidate = repo_cache / "snapshots" / spec.revision
    try:
        if not candidate.is_dir() or not _is_verified_hub_snapshot(candidate, spec):
            return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved


def resolve_model_path(data_dir: Path, profile: str) -> Path | None:
    """Find a complete model for ``balanced``/``medium`` or ``fast``/``small``.

    Searches the app's conventional data directory first, then ``HF_HUB_CACHE``,
    ``HF_HOME/hub``, and Hugging Face's default cache. App-local models require
    the provenance manifest written by setup. Hub snapshots must use the exact
    pinned revision and a cache chain protected from untrusted replacement;
    content-addressed blob links are checked against their ETags. No directory
    is created and no network request is made.
    """
    spec = model_spec(profile)
    model_dir = Path(data_dir).expanduser() / "models"
    local_candidates = (
        model_dir / spec.size,
        model_dir / spec.model_name,
        model_dir / f"faster-whisper-{spec.size}",
    )
    for candidate in local_candidates:
        if is_compatible_model_path(candidate, spec):
            return candidate.resolve()

    repo_cache_name = "models--" + spec.repository.replace("/", "--")
    for cache_root in _hub_cache_roots(Path(data_dir).expanduser()):
        resolved = _valid_snapshot(cache_root / repo_cache_name, spec)
        if resolved is not None:
            return resolved
    return None

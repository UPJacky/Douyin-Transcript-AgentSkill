from __future__ import annotations

import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from douyin_transcript import storage_security
from douyin_transcript.storage_security import (
    PrivateStorageError,
    create_private_file,
    ensure_private_directory,
    inspect_private_path,
    open_private_regular_file,
)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_new_directory_and_file_receive_private_posix_modes(tmp_path):
    directory = ensure_private_directory(tmp_path / "new" / "private")
    path = directory / "tasks.sqlite3"

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert create_private_file(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert inspect_private_path(directory).status == "private"
    assert inspect_private_path(path).status == "private"


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX directory-handle identity regression"
)
def test_posix_pinned_directory_chain_detects_replaced_component(tmp_path):
    target = ensure_private_directory(tmp_path / "parent" / "leaf")
    descriptors = storage_security._open_posix_directory_chain(
        target, create_missing=False
    )
    parent = target.parent
    moved_parent = tmp_path / "parent-original"
    try:
        parent.rename(moved_parent)
        parent.mkdir(mode=0o700)

        with pytest.raises(PrivateStorageError, match="检查期间被替换"):
            storage_security._verify_posix_directory_chain(target, descriptors)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@pytest.mark.skipif(os.name == "nt", reason="POSIX dir_fd-relative create regression")
def test_posix_file_create_uses_pinned_parent_and_detects_replacement(
    monkeypatch, tmp_path
):
    parent = ensure_private_directory(tmp_path / "parent")
    target = parent / "tasks.sqlite3"
    moved_parent = tmp_path / "parent-original"
    real_open_chain = storage_security._open_posix_directory_chain

    def open_then_replace(path, *, create_missing):
        descriptors = real_open_chain(path, create_missing=create_missing)
        if path == parent:
            parent.rename(moved_parent)
            parent.mkdir(mode=0o700)
        return descriptors

    monkeypatch.setattr(
        storage_security, "_open_posix_directory_chain", open_then_replace
    )

    with pytest.raises(PrivateStorageError, match="检查期间被替换") as error:
        create_private_file(target)

    assert "对象可能仍保留" in str(error.value)
    assert "核对对象身份后再清理" in str(error.value)
    assert not target.exists()
    assert stat.S_IMODE((moved_parent / target.name).stat().st_mode) == 0o600


def test_task_database_and_live_sqlite_sidecars_are_private(tmp_path):
    from douyin_transcript.tasks import TaskStore

    database = tmp_path / "private" / "tasks.sqlite3"
    with TaskStore(database):
        assert inspect_private_path(database).status == "private"
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = type(database)(f"{database}{suffix}")
            if sidecar.exists():
                assert inspect_private_path(sidecar).status == "private"


def test_canonical_storage_path_rejects_traversal_before_normalization(
    monkeypatch, tmp_path
):
    target = tmp_path / "alias" / "nested" / ".." / "private"
    monkeypatch.setattr(
        storage_security.Path,
        "resolve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not resolve")
        ),
    )

    with pytest.raises(ValueError, match=r"\.\."):
        storage_security._canonical_storage_path(target)


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-type policy")
@pytest.mark.parametrize(
    ("drive_type", "message"),
    [
        (0, "无法确认敏感存储驱动器"),  # DRIVE_UNKNOWN
        (1, "无法确认敏感存储驱动器"),  # DRIVE_NO_ROOT_DIR
        (4, "映射网络驱动器"),  # DRIVE_REMOTE
    ],
)
def test_canonical_storage_path_rejects_remote_or_unknown_drives(
    monkeypatch, drive_type, message
):
    roots = []

    def drive_type_for_root(root):
        roots.append(root)
        return drive_type

    monkeypatch.setattr(storage_security, "_windows_drive_type", drive_type_for_root)

    with pytest.raises(ValueError, match=message):
        storage_security._canonical_storage_path(r"Z:\\private")

    assert roots == ["Z:\\"]


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-type policy")
def test_canonical_storage_path_accepts_local_drive(monkeypatch):
    roots = []

    def local_drive(root):
        roots.append(root)
        return 3  # DRIVE_FIXED

    monkeypatch.setattr(storage_security, "_windows_drive_type", local_drive)

    assert storage_security._canonical_storage_path(r"C:\\private") == Path(
        r"C:\\private"
    )
    assert roots == ["C:\\"]


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-type policy")
def test_storage_path_diagnostics_explain_remote_drive(monkeypatch):
    monkeypatch.setattr(storage_security, "_windows_drive_type", lambda _root: 4)

    report = inspect_private_path(r"Z:\\private")

    assert report.status == "unknown"
    assert "映射网络驱动器" in report.detail


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-type policy")
def test_storage_creation_error_explains_remote_drive(monkeypatch):
    monkeypatch.setattr(storage_security, "_windows_drive_type", lambda _root: 4)

    with pytest.raises(PrivateStorageError, match="映射网络驱动器"):
        ensure_private_directory(r"Z:\\private")


def test_inspector_rejects_symlink_path_without_resolving_target(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {type(exc).__name__}")

    report = inspect_private_path(alias / "sensitive")

    assert report.status == "unknown"
    assert "符号链接" in report.detail


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX pinned descriptor replacement regression"
)
def test_private_config_reader_keeps_the_checked_file_open(tmp_path):
    path = tmp_path / "config.toml"
    replacement = tmp_path / "replacement.toml"
    path.write_bytes(b"[paths]\noutput_dir = 'checked'\n")
    replacement.write_bytes(b"[paths]\noutput_dir = 'replaced'\n")
    path.chmod(0o600)
    replacement.chmod(0o600)

    with open_private_regular_file(path) as stream:
        os.replace(replacement, path)
        assert b"output_dir = 'checked'" in stream.read()

    assert b"output_dir = 'replaced'" in path.read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFO regression")
def test_private_config_reader_rejects_fifo_without_waiting_for_a_writer(tmp_path):
    path = tmp_path / "config.toml"
    os.mkfifo(path, 0o600)
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from douyin_transcript.storage_security import "
        "PrivateStorageError, open_private_regular_file\n"
        "try:\n"
        "    open_private_regular_file(Path(sys.argv[1]))\n"
        "except PrivateStorageError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(1)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", code, str(path)])
    try:
        return_code = process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        pytest.fail("config reader blocked while opening a FIFO")

    assert return_code == 0


def test_private_config_reader_rejects_dotdot_component(tmp_path):
    path = tmp_path / "private" / "config.toml"
    with pytest.raises(PrivateStorageError):
        open_private_regular_file(path.parent / ".." / "private" / path.name)


def test_missing_sensitive_path_checks_existing_ancestor_policy(monkeypatch, tmp_path):
    target = tmp_path / "missing-parent" / "sensitive"

    if os.name == "nt":
        monkeypatch.setattr(
            storage_security,
            "_inspect_windows_ancestor_path",
            lambda path: storage_security.PermissionReport("shared", "unsafe ancestor")
            if path == tmp_path
            else storage_security.PermissionReport("private", "trusted ancestor"),
        )
    else:
        monkeypatch.setattr(
            storage_security,
            "_inspect_posix_ancestor",
            lambda path, _info: storage_security.PermissionReport(
                "shared", "unsafe ancestor"
            )
            if path == tmp_path
            else storage_security.PermissionReport("private", "trusted ancestor"),
        )

    report = inspect_private_path(target)

    assert report.status == "shared"
    assert "unsafe ancestor" in report.detail


def test_concurrent_task_store_opening_survives_wal_sidecar_lifecycle(tmp_path):
    from douyin_transcript.tasks import TaskStore

    database = tmp_path / "private" / "tasks.sqlite3"

    def create_task(index: int) -> str:
        with TaskStore(database) as store:
            task = store.create_remote_task(
                f"https://www.douyin.com/video/{index}", str(index)
            )
            return task.task_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        task_ids = list(executor.map(create_task, range(1, 25)))

    assert len(task_ids) == 24
    with TaskStore(database) as store:
        assert len(store.list_tasks()) == 24


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_existing_shared_directory_is_rejected_without_chmod(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)

    with pytest.raises(PrivateStorageError, match="已有权限未修改"):
        ensure_private_directory(shared)

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_exclusive_create_does_not_change_an_existing_file(tmp_path):
    existing = tmp_path / "existing.sqlite3"
    existing.write_bytes(b"user data")
    existing.chmod(0o644)

    assert not create_private_file(existing)

    assert stat.S_IMODE(existing.stat().st_mode) == 0o644
    assert existing.read_bytes() == b"user data"


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_task_store_refuses_existing_shared_directory_without_changing_it(tmp_path):
    from douyin_transcript.tasks import TaskStore

    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)

    with pytest.raises(PrivateStorageError):
        TaskStore(shared / "tasks.sqlite3")

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert not (shared / "tasks.sqlite3").exists()


@pytest.mark.parametrize(
    ("path_mode", "owner_uid", "expected_status"),
    [
        (stat.S_IFREG | 0o600, 1000, "private"),
        (stat.S_IFREG | 0o600, 1001, "shared"),
        (stat.S_IFDIR | 0o700, 1000, "private"),
        (stat.S_IFDIR | 0o700, 1001, "shared"),
    ],
)
def test_posix_inspector_checks_owner_for_files_and_parent_directories(
    monkeypatch, tmp_path, path_mode, owner_uid, expected_status
):
    # Mock stat and the POSIX identity so this policy also runs on Windows.
    target = tmp_path / "sensitive-path"
    info = SimpleNamespace(st_mode=path_mode, st_uid=owner_uid)
    real_lstat = storage_security.Path.lstat
    monkeypatch.setattr(
        storage_security,
        "os",
        SimpleNamespace(name="posix", path=os.path, geteuid=lambda: 1000),
    )
    monkeypatch.setattr(
        storage_security, "_canonical_storage_path", lambda _path: target
    )
    monkeypatch.setattr(
        storage_security,
        "_inspect_posix_ancestor",
        lambda _path, _info: storage_security.PermissionReport(
            "private", "test ancestor"
        ),
    )
    monkeypatch.setattr(
        storage_security.Path,
        "lstat",
        lambda path: info if path == target else real_lstat(path),
    )

    report = inspect_private_path(target)

    assert report.status == expected_status
    if owner_uid != 1000:
        assert "所有者 UID" in report.detail


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-handle regression")
def test_ensure_private_directory_rejects_foreign_owned_existing_parent(
    monkeypatch, tmp_path
):
    # TaskStore and other callers validate their sensitive parent directory here.
    existing = tmp_path / "private-data"
    existing.mkdir(mode=0o700)
    real_inspect = storage_security._inspect_posix_ancestor
    monkeypatch.setattr(
        storage_security,
        "_inspect_posix_ancestor",
        lambda path, info: storage_security.PermissionReport(
            "shared", "祖先目录所有者 UID 为 1001"
        )
        if path == existing
        else real_inspect(path, info),
    )

    with pytest.raises(PrivateStorageError, match="所有者 UID"):
        ensure_private_directory(existing)


@pytest.mark.parametrize(
    ("owner_uid", "mode", "expected_status"),
    [
        (0, 0o755, "private"),
        (1000, 0o755, "private"),
        (0, 0o1777, "private"),
        (0, 0o777, "shared"),
        (1001, 0o755, "shared"),
    ],
)
def test_posix_ancestor_policy_allows_trusted_and_sticky_directories(
    monkeypatch, tmp_path, owner_uid, mode, expected_status
):
    monkeypatch.setattr(
        storage_security,
        "os",
        SimpleNamespace(name="posix", path=os.path, geteuid=lambda: 1000),
    )
    info = SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=owner_uid)

    report = storage_security._inspect_posix_ancestor(tmp_path, info)

    assert report.status == expected_status


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_task_store_creates_private_database_and_refuses_shared_existing_db(tmp_path):
    from douyin_transcript.tasks import TaskStore

    database = tmp_path / "tasks.sqlite3"
    with TaskStore(database):
        pass
    assert stat.S_IMODE(database.stat().st_mode) == 0o600

    existing = tmp_path / "legacy.sqlite3"
    existing.write_bytes(b"existing database")
    existing.chmod(0o644)
    with pytest.raises(PrivateStorageError, match="程序不会更改已有权限"):
        TaskStore(existing)
    assert stat.S_IMODE(existing.stat().st_mode) == 0o644
    assert existing.read_bytes() == b"existing database"


def test_windows_owner_policy_rejects_foreign_owner_and_accepts_trusted_owners():
    current_sid = "S-1-5-21-100-200-300-1001"

    assert storage_security._check_windows_owner(current_sid, current_sid) is None
    assert storage_security._check_windows_owner("S-1-5-18", current_sid) is None
    assert storage_security._check_windows_owner("S-1-5-32-544", current_sid) is None

    report = storage_security._check_windows_owner(
        "S-1-5-21-100-200-300-1002", current_sid
    )
    assert report is not None
    assert report.status == "shared"
    assert "路径所有者" in report.detail


@pytest.mark.parametrize(
    ("access_mask", "sensitive"),
    [
        (0x00000020, False),  # FILE_EXECUTE / directory traversal
        (0x00100000, False),  # SYNCHRONIZE
        (0x00100020, False),  # traversal and synchronization only
        (0x00000001, True),  # FILE_READ_DATA / directory listing
        (0x00000002, True),  # FILE_WRITE_DATA
        (0x00000040, True),  # FILE_DELETE_CHILD
        (0x80000000, True),  # GENERIC_READ
    ],
)
def test_windows_foreign_ace_policy_distinguishes_traversal_from_data_access(
    access_mask, sensitive
):
    assert (
        storage_security._foreign_windows_ace_grants_sensitive_access(access_mask)
        is sensitive
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL test")
def test_windows_temp_directory_with_owner_rights_is_private(tmp_path):
    # Pytest's Windows temp ACL uses OWNER RIGHTS instead of a direct user ACE.
    # The security check allows the current process token's SID as an owner.
    report = inspect_private_path(tmp_path)
    assert report.status == "private", report.detail
    assert storage_security._current_user_sid().startswith("S-")


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL test")
def test_windows_new_storage_is_protected_and_unknown_is_rejected(
    monkeypatch, tmp_path
):
    directory = ensure_private_directory(tmp_path / "private")
    assert inspect_private_path(directory).status == "private"

    monkeypatch.setattr(
        storage_security,
        "_inspect_windows_handle",
        lambda _path: storage_security.PermissionReport("unknown", "unparseable ACE"),
    )
    with pytest.raises(PrivateStorageError, match="unparseable ACE"):
        ensure_private_directory(directory)


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive-create regression")
def test_windows_exclusive_create_leaves_existing_file_unchanged(tmp_path):
    directory = ensure_private_directory(tmp_path / "private")
    existing = directory / "existing.sqlite3"
    existing.write_bytes(b"user data")

    assert not create_private_file(existing)
    assert existing.read_bytes() == b"user data"


@pytest.mark.skipif(os.name != "nt", reason="Windows handle identity regression")
def test_windows_directory_creation_detects_replaced_parent(monkeypatch, tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    target = parent / "nested"
    moved_parent = tmp_path / "parent-original"
    real_create = storage_security._create_windows_private_directory

    def create_then_replace(path):
        real_create(path)
        if path == target:
            parent.rename(moved_parent)
            parent.mkdir()

    monkeypatch.setattr(
        storage_security, "_create_windows_private_directory", create_then_replace
    )

    with pytest.raises(PrivateStorageError, match="检查期间被替换") as exc_info:
        ensure_private_directory(target)

    assert "新建私有目录，失败后对象可能仍保留" in str(exc_info.value)
    assert not target.exists()
    assert (moved_parent / target.name).is_dir()


@pytest.mark.skipif(os.name != "nt", reason="Windows file identity regression")
def test_windows_file_create_fails_closed_on_leaf_identity_mismatch(
    monkeypatch, tmp_path
):
    directory = ensure_private_directory(tmp_path / "private")
    target = directory / "tasks.sqlite3"
    real_open_object = storage_security._open_windows_object_handle
    real_identity = storage_security._windows_handle_identity
    path_handle = None

    def capture_path_handle(path):
        nonlocal path_handle
        handle = real_open_object(path)
        if path == target:
            path_handle = handle
        return handle

    def mismatch_path_identity(handle):
        identity = real_identity(handle)
        if path_handle == handle:
            return (*identity[:2], identity[2] ^ 1)
        return identity

    monkeypatch.setattr(
        storage_security, "_open_windows_object_handle", capture_path_handle
    )
    monkeypatch.setattr(
        storage_security, "_windows_handle_identity", mismatch_path_identity
    )

    with pytest.raises(
        PrivateStorageError, match="敏感文件在检查期间被替换"
    ) as exc_info:
        create_private_file(target)

    assert "新建私有文件，失败后对象可能仍保留" in str(exc_info.value)
    assert path_handle is not None
    assert target.exists()

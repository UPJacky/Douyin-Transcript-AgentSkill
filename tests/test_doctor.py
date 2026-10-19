from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from douyin_transcript import config, doctor


def test_default_data_dir_uses_platform_location(monkeypatch, tmp_path):
    monkeypatch.delenv("DOUYIN_TRANSCRIPT_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if os.name == "nt":
        # This unit test covers platform path selection. ACL policy has separate
        # tests because pytest's temp root may itself be intentionally shared.
        monkeypatch.setattr(
            doctor,
            "inspect_private_path",
            lambda _path: SimpleNamespace(status="missing"),
        )

    path = doctor.default_data_dir()

    if os.name == "nt":
        assert path == tmp_path / "douyin-transcript"
    else:
        assert path.name == "douyin-transcript"


def test_windows_default_falls_back_when_local_appdata_ancestors_are_unsafe(
    monkeypatch, tmp_path
):
    local_app_data = tmp_path / "AppData" / "Local"
    profile = tmp_path / "profile"
    expected = profile / ".local" / "share" / "douyin-transcript"
    monkeypatch.setattr(
        doctor,
        "os",
        SimpleNamespace(name="nt", environ={"LOCALAPPDATA": str(local_app_data)}),
    )
    monkeypatch.setattr(Path, "home", lambda: profile)
    monkeypatch.setattr(
        doctor,
        "inspect_private_path",
        lambda path: SimpleNamespace(
            status="shared"
            if Path(path) == local_app_data / "douyin-transcript"
            else "missing"
        ),
    )

    assert doctor.default_data_dir() == expected


def test_windows_default_does_not_hide_existing_unsafe_localappdata(
    monkeypatch, tmp_path
):
    local_app_data = tmp_path / "AppData" / "Local" / "douyin-transcript"
    local_app_data.mkdir(parents=True)
    monkeypatch.setattr(
        doctor,
        "os",
        SimpleNamespace(
            name="nt", environ={"LOCALAPPDATA": str(local_app_data.parent)}
        ),
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "profile")
    monkeypatch.setattr(
        doctor,
        "inspect_private_path",
        lambda _path: SimpleNamespace(status="shared"),
    )

    assert doctor.default_data_dir() == local_app_data


def test_data_home_override_is_respected(monkeypatch, tmp_path):
    custom = tmp_path / "custom-store"
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(custom))

    assert doctor.default_data_dir() == custom


def test_doctor_never_creates_user_data_directory(monkeypatch, tmp_path):
    data_dir = tmp_path / "not-created"
    monkeypatch.setattr(
        doctor, "_module_status", lambda name: {"status": "missing", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda path, profile: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda status: {"status": "missing", "detail": "test"},
    )

    report = doctor.collect_report(str(data_dir))

    assert report["overall"] == "setup_required"
    assert report["checks"]["faster_whisper"]["status"] == "missing"
    assert report["checks"]["model"]["status"] == "missing"
    assert report["checks"]["playwright"]["status"] == "missing"
    assert report["checks"]["chromium"]["status"] == "missing"
    assert not data_dir.exists()


def test_doctor_checks_explicit_output_dir_without_creating_it(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "selected-output"
    seen = []
    monkeypatch.setattr(
        doctor,
        "_module_status",
        lambda _name: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda _path, _profile: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda _status: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_directory_status",
        lambda _path: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_disk_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "output_directory_permission_status",
        lambda path: seen.append(Path(path))
        or {"status": "unsafe", "detail": "shared parent"},
    )

    report = doctor.collect_report(str(data_dir), output_dir_override=str(output_dir))

    assert report["output_dir"] == str(output_dir.resolve())
    assert report["checks"]["output_dir_permissions"]["status"] == "unsafe"
    assert seen == [output_dir.resolve()]
    assert not output_dir.exists()


def test_doctor_does_not_check_current_directory_for_empty_output_override(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "data"
    checked_directories = []
    checked_output_permissions = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "default_data_dir", lambda: data_dir)
    monkeypatch.setattr(
        doctor,
        "_module_status",
        lambda _name: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda _path, _profile: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda _status: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_directory_status",
        lambda path: checked_directories.append(Path(path))
        or {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "output_directory_permission_status",
        lambda path: checked_output_permissions.append(Path(path))
        or {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_permission_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_disk_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )

    report = doctor.collect_report(output_dir_override="")

    assert report["output_dir"] == ""
    assert report["checks"]["config"]["status"] == "invalid"
    assert report["checks"]["output_dir"]["status"] == "unknown"
    assert report["checks"]["output_dir_permissions"]["status"] == "unknown"
    assert checked_directories == [data_dir]
    assert checked_output_permissions == []
    assert tmp_path.resolve() not in checked_directories
    assert not data_dir.exists()


def _stub_doctor_probes(monkeypatch, checked_directories, checked_output_permissions):
    monkeypatch.setattr(
        doctor,
        "_module_status",
        lambda _name: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda _path, _profile: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda _status: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_directory_status",
        lambda path: checked_directories.append(Path(path))
        or {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "output_directory_permission_status",
        lambda path: checked_output_permissions.append(Path(path))
        or {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_permission_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_disk_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )


def test_doctor_uses_explicit_output_environment_override_on_config_error(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "configured-output"
    checked_directories = []
    checked_output_permissions = []

    def fail_resolve_paths(**_kwargs):
        raise config.ConfigurationError("config.toml [limits] 配置无效：错误值")

    monkeypatch.setattr(config, "resolve_paths", fail_resolve_paths)
    monkeypatch.setattr(doctor, "default_data_dir", lambda: data_dir)
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_OUTPUT", str(output_dir))
    _stub_doctor_probes(monkeypatch, checked_directories, checked_output_permissions)

    report = doctor.collect_report()

    assert report["output_dir"] == str(output_dir.resolve())
    assert report["checks"]["config"] == {
        "status": "invalid",
        "detail": "config.toml [limits] 配置无效：错误值",
    }
    assert checked_directories == [data_dir, output_dir.resolve()]
    assert checked_output_permissions == [output_dir.resolve()]
    assert not output_dir.exists()


def test_doctor_does_not_guess_output_path_for_other_config_errors(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "data"
    guessed_output = data_dir / "output"
    checked_directories = []
    checked_output_permissions = []

    def fail_resolve_paths(**_kwargs):
        raise config.ConfigurationError("config.toml 格式无效：配置语法错误")

    monkeypatch.setattr(config, "resolve_paths", fail_resolve_paths)
    monkeypatch.setattr(doctor, "default_data_dir", lambda: data_dir)
    monkeypatch.delenv("DOUYIN_TRANSCRIPT_OUTPUT", raising=False)
    monkeypatch.chdir(tmp_path)
    _stub_doctor_probes(monkeypatch, checked_directories, checked_output_permissions)

    report = doctor.collect_report()

    assert report["output_dir"] == ""
    assert report["checks"]["config"] == {
        "status": "invalid",
        "detail": "config.toml 格式无效：配置语法错误",
    }
    assert report["checks"]["output_dir"]["status"] == "unknown"
    assert report["checks"]["output_dir_permissions"]["status"] == "unknown"
    assert checked_directories == [data_dir]
    assert checked_output_permissions == []
    assert guessed_output not in checked_directories
    assert not guessed_output.exists()


def test_module_check_reports_import_error_as_broken(monkeypatch, tmp_path):
    (tmp_path / "broken_audit_dependency.py").write_text(
        "raise ImportError('broken for audit test')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))

    result = doctor._module_status("broken_audit_dependency")

    assert result["status"] == "broken"
    assert result["detail"] == "ImportError"


def test_module_check_does_not_import_shadow_module_from_working_directory(
    monkeypatch, tmp_path
):
    marker = tmp_path / "shadow-imported.txt"
    (tmp_path / "json.py").write_text(
        f"open({str(marker)!r}, 'w', encoding='utf-8').write('executed')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = doctor._module_status("json")

    assert result["status"] == "ok"
    assert not marker.exists()


def test_doctor_python_probes_use_safe_path_mode(monkeypatch):
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="C:/chromium.exe\n", stderr="")

    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    assert doctor._module_status("fake_dependency")["status"] == "ok"
    assert doctor._chromium_executable() == Path("C:/chromium.exe")
    assert len(calls) == 2
    assert all(args[1] == "-P" for args in calls)


def test_cli_outputs_utf8_when_windows_default_is_legacy(monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    cli = [sys.executable, "-m", "douyin_transcript"]

    help_result = subprocess.run(
        [*cli, "--help"], capture_output=True, env=os.environ.copy(), check=False
    )
    doctor_result = subprocess.run(
        [*cli, "doctor", "--json"],
        capture_output=True,
        env=os.environ.copy(),
        check=False,
    )

    help_text = help_result.stdout.decode("utf-8")
    doctor_text = doctor_result.stdout.decode("utf-8")
    report = json.loads(doctor_text)
    assert help_result.returncode == 0
    assert "检查运行环境" in help_text
    assert report["overall"] in {"ready", "setup_required"}
    assert doctor_result.returncode == (0 if report["overall"] == "ready" else 1)


def test_doctor_separates_local_and_url_capabilities(monkeypatch, tmp_path):
    monkeypatch.setattr(
        doctor,
        "_module_status",
        lambda name: {
            "status": "missing" if name == "playwright" else "ok",
            "detail": "test",
        },
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda path, profile: {"status": "ok", "detail": profile},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda status: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor, "_directory_status", lambda path: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor, "_disk_status", lambda path: {"status": "ok", "detail": "test"}
    )

    report = doctor.collect_report(str(tmp_path / "data"), profile="fast")

    assert report["overall"] == "ready"
    assert report["capabilities"] == {
        "local_transcription": "ready",
        "douyin_urls": "setup_required",
    }
    assert report["checks"]["model"]["detail"] == "fast"


def test_doctor_personal_url_capability_uses_installed_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(
        doctor, "_module_status", lambda _name: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda _path, profile: {"status": "ok", "detail": profile},
    )
    monkeypatch.setattr(
        doctor, "_chromium_status", lambda _status: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor, "_directory_status", lambda _path: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor, "_permission_status", lambda _path: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor, "_disk_status", lambda _path: {"status": "ok", "detail": "test"}
    )

    report = doctor.collect_report(
        str(tmp_path / "data"),
        profile="fast",
        output_dir_override=str(tmp_path / "output"),
    )

    assert report["capabilities"]["local_transcription"] == "ready"
    assert report["capabilities"]["douyin_urls"] == "ready"
    assert report["capture_mode"] == "personal"
    assert report["checks"]["browser_isolation"] == {
        "status": "not_used",
        "detail": "个人模式使用当前账号的 Chromium；不使用管理员 WFP 服务",
    }


def test_doctor_marks_bad_config_without_creating_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text("[paths\n", encoding="utf-8")
    monkeypatch.setattr(
        doctor, "_module_status", lambda name: {"status": "missing", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda path, profile: {"status": "missing", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor,
        "_chromium_status",
        lambda status: {"status": "missing", "detail": "test"},
    )

    report = doctor.collect_report(str(data_dir))

    assert report["checks"]["config"]["status"] == "invalid"
    assert report["overall"] == "setup_required"
    assert not (data_dir / "tasks.sqlite3").exists()


def test_doctor_reports_shared_data_directory_without_changing_it(
    monkeypatch, tmp_path
):
    if os.name == "nt":
        return
    data_dir = tmp_path / "shared-data"
    data_dir.mkdir()
    data_dir.chmod(0o755)
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(data_dir))
    monkeypatch.setattr(
        doctor, "_module_status", lambda name: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor,
        "_model_status",
        lambda path, profile: {"status": "ok", "detail": "test"},
    )
    monkeypatch.setattr(
        doctor, "_chromium_status", lambda status: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor, "_directory_status", lambda path: {"status": "ok", "detail": "test"}
    )
    monkeypatch.setattr(
        doctor, "_disk_status", lambda path: {"status": "ok", "detail": "test"}
    )

    report = doctor.collect_report()

    assert report["checks"]["data_dir_permissions"]["status"] == "unsafe"
    assert report["checks"]["task_database_permissions"]["status"] == "unsafe"
    assert report["capabilities"]["local_transcription"] == "setup_required"
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o755
    assert not (data_dir / "tasks.sqlite3").exists()


def test_output_directory_permission_check_is_advisory_for_shared_folder(
    monkeypatch, tmp_path
):
    output_dir = tmp_path / "shared-output"
    output_dir.mkdir()
    output_dir.chmod(0o755)
    initial_mode = stat.S_IMODE(output_dir.stat().st_mode)
    monkeypatch.setattr(
        doctor,
        "inspect_private_path",
        lambda path: SimpleNamespace(status="shared", detail="shared ACL"),
    )

    result = doctor._output_directory_permission_status(output_dir)

    assert result["status"] == "unsafe"
    assert "shared ACL" in result["detail"]
    assert stat.S_IMODE(output_dir.stat().st_mode) == initial_mode


def test_missing_output_directory_checks_nearest_existing_parent(monkeypatch, tmp_path):
    parent = tmp_path / "shared-parent"
    parent.mkdir()
    output_dir = parent / "not-created"
    seen_paths = []

    def inspect(path):
        seen_paths.append(Path(path))
        return SimpleNamespace(status="shared", detail="shared ACL")

    monkeypatch.setattr(doctor, "inspect_private_path", inspect)

    result = doctor._output_directory_permission_status(output_dir)

    assert seen_paths == [parent]
    assert result["status"] == "unsafe"
    assert "shared ACL" in result["detail"]
    assert not output_dir.exists()


def test_sensitive_path_with_unsafe_ancestor_is_reported_unsafe(monkeypatch, tmp_path):
    target = tmp_path / "not-created" / "data"
    seen_paths = []

    def inspect(path):
        path = Path(path)
        seen_paths.append(path)
        return SimpleNamespace(status="shared", detail="shared ancestor")

    monkeypatch.setattr(doctor, "inspect_private_path", inspect)

    result = doctor._permission_status(target)

    assert result["status"] == "unsafe"
    assert "shared ancestor" in result["detail"]
    assert seen_paths == [target]
    assert not target.exists()

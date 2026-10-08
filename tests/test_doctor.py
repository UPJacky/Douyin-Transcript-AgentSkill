from __future__ import annotations

from douyin_transcript.doctor import collect_report, default_data_dir


def test_doctor_reports_unimplemented_runtime_dependencies(tmp_path):
    report = collect_report(str(tmp_path / "user-data"))

    assert report["project"] == "douyin-transcript"
    assert report["overall"] in {"ready", "setup_required"}
    assert report["checks"]["python"]["status"] in {"ok", "missing"}
    assert report["checks"]["model"]["status"] in {"ok", "missing"}
    assert report["checks"]["chromium"]["status"] in {"ok", "missing"}
    assert not (tmp_path / "user-data").exists()


def test_default_data_dir_is_platform_path():
    path = default_data_dir()

    assert path.name == "douyin-transcript"

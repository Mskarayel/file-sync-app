"""Rapor üretimi testleri (UI'sız, tmp_path ile)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import report_manager  # noqa: E402
from app.models import FileComparison, FileStatus, SyncSummary  # noqa: E402


def _make_summary() -> SyncSummary:
    start = datetime(2026, 7, 16, 10, 0, 0)
    end = datetime(2026, 7, 16, 10, 0, 5)
    return SyncSummary(
        source=Path("kaynak"),
        target=Path("hedef"),
        started_at=start,
        finished_at=end,
        comparisons=[
            FileComparison(Path("belge2.txt"), FileStatus.NEW, 28),
            FileComparison(Path("belge1.txt"), FileStatus.MODIFIED, 21),
            FileComparison(Path("belgeler/notlar.txt"), FileStatus.SAME, 25),
            FileComparison(Path("kilitli.txt"), FileStatus.ERROR, 0, "erişim engellendi"),
        ],
    )


def test_save_reports_iki_dosya_olusturur(tmp_path):
    summary = _make_summary()
    paths = report_manager.save_reports(summary, reports_dir=tmp_path)
    assert paths["txt"].exists()
    assert paths["json"].exists()
    # Dosya adında tarih-saat bulunmalı.
    assert paths["txt"].name.startswith("sync_report_")


def test_json_gecerli_ve_tam(tmp_path):
    summary = _make_summary()
    paths = report_manager.save_reports(summary, reports_dir=tmp_path, formats=["json"])
    data = json.loads(paths["json"].read_text(encoding="utf-8"))

    assert data["source"] == "kaynak"
    assert data["target"] == "hedef"
    assert data["duration_seconds"] == 5.0
    assert data["totals"] == {"total": 4, "new": 1, "modified": 1, "same": 1, "error": 1}
    assert len(data["files"]) == 4
    error_file = next(f for f in data["files"] if f["status"] == "error")
    assert error_file["error_message"] == "erişim engellendi"


def test_txt_temel_bilgileri_icerir(tmp_path):
    summary = _make_summary()
    paths = report_manager.save_reports(summary, reports_dir=tmp_path, formats=["txt"])
    text = paths["txt"].read_text(encoding="utf-8")
    assert "Kaynak klasör" in text
    assert "Toplam süre" in text
    assert "belge2.txt" in text
    assert "erişim engellendi" in text


def test_yalniz_json_formati(tmp_path):
    summary = _make_summary()
    paths = report_manager.save_reports(summary, reports_dir=tmp_path, formats=["json"])
    assert "json" in paths
    assert "txt" not in paths


def test_yazma_hatasi_report_error_yukseltir(tmp_path, monkeypatch):
    summary = _make_summary()

    def boom(*args, **kwargs):
        raise OSError("disk dolu")

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(report_manager.ReportError):
        report_manager.save_reports(summary, reports_dir=tmp_path)

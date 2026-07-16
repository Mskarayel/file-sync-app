"""Senkronizasyon motoru ve doğrulama testleri (UI'sız)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sync_engine  # noqa: E402
from app.models import FileStatus  # noqa: E402
from app.validators import validate_folders  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _status_of(summary, rel_name: str) -> FileStatus:
    for comparison in summary.comparisons:
        if str(comparison.relative_path) == rel_name:
            return comparison.status
    raise AssertionError(f"{rel_name} bulunamadı")


@pytest.fixture
def folders(tmp_path: Path):
    source = tmp_path / "kaynak"
    target = tmp_path / "hedef"
    source.mkdir()
    target.mkdir()
    return source, target


def test_eksik_dosya_tespiti(folders):
    source, target = folders
    _write(source / "a.txt", "merhaba")
    summary = sync_engine.analyze(source, target)
    assert _status_of(summary, "a.txt") is FileStatus.NEW
    assert summary.new_count == 1


def test_degismis_dosya_farkli_boyut(folders):
    source, target = folders
    _write(source / "a.txt", "uzun içerik")
    _write(target / "a.txt", "kısa")
    summary = sync_engine.analyze(source, target)
    assert _status_of(summary, "a.txt") is FileStatus.MODIFIED


def test_degismis_dosya_ayni_boyut_farkli_icerik(folders):
    source, target = folders
    _write(source / "a.txt", "AAAA")
    _write(target / "a.txt", "BBBB")  # Aynı boyut, farklı içerik.
    # mtime'ı belirgin şekilde farklılaştır ki hash yoluna girsin.
    old = time.time() - 100
    os.utime(target / "a.txt", (old, old))
    summary = sync_engine.analyze(source, target)
    assert _status_of(summary, "a.txt") is FileStatus.MODIFIED


def test_ayni_dosya(folders):
    source, target = folders
    _write(source / "a.txt", "aynı içerik")
    _write(target / "a.txt", "aynı içerik")
    stat = (source / "a.txt").stat()
    os.utime(target / "a.txt", (stat.st_atime, stat.st_mtime))
    summary = sync_engine.analyze(source, target)
    assert _status_of(summary, "a.txt") is FileStatus.SAME
    assert summary.same_count == 1


def test_alt_klasor_destegi(folders):
    source, target = folders
    _write(source / "belgeler" / "notlar.txt", "alt klasör")
    summary = sync_engine.analyze(source, target)
    rel = str(Path("belgeler") / "notlar.txt")
    assert _status_of(summary, rel) is FileStatus.NEW


def test_ayni_kaynak_hedef_reddedilir(tmp_path):
    folder = tmp_path / "ortak"
    folder.mkdir()
    result = validate_folders(folder, folder)
    assert not result.ok


def test_ic_ice_klasor_reddedilir(tmp_path):
    source = tmp_path / "kaynak"
    target = source / "ic_hedef"
    target.mkdir(parents=True)
    result = validate_folders(source, target)
    assert not result.ok


def test_kopyalama_sonrasi_dosya_olusur(folders):
    source, target = folders
    _write(source / "belgeler" / "notlar.txt", "içerik")
    plan = sync_engine.analyze(source, target)
    sync_engine.synchronize(plan)
    copied = target / "belgeler" / "notlar.txt"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "içerik"
    # copy2 zaman bilgisini korumalı.
    assert abs(copied.stat().st_mtime - (source / "belgeler" / "notlar.txt").stat().st_mtime) < 2


def test_hata_durumunda_devam(folders, monkeypatch):
    source, target = folders
    _write(source / "iyi.txt", "iyi")
    _write(source / "bozuk.txt", "bozuk")
    plan = sync_engine.analyze(source, target)

    real_copy = sync_engine.shutil.copy2

    def fake_copy(src, dst, *args, **kwargs):
        if str(src).endswith("bozuk.txt"):
            raise OSError("erişim engellendi")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(sync_engine.shutil, "copy2", fake_copy)
    result = sync_engine.synchronize(plan)

    assert (target / "iyi.txt").exists()          # Hataya rağmen devam etti.
    assert _status_of(result, "iyi.txt") is FileStatus.NEW
    assert _status_of(result, "bozuk.txt") is FileStatus.ERROR
    assert result.error_count == 1

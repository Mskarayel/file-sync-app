"""Kenar durum testleri: boş klasör, Türkçe/uzun adlar, sayımlar, içerik eşitliği."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import report_manager, sync_engine  # noqa: E402
from app.models import FileComparison, FileStatus, SyncSummary  # noqa: E402


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def folders(tmp_path: Path):
    source = tmp_path / "kaynak"
    target = tmp_path / "hedef"
    source.mkdir()
    target.mkdir()
    return source, target


def test_bos_kaynak_klasor_sifir_dosya(folders):
    source, target = folders
    summary = sync_engine.analyze(source, target)
    assert summary.total_count == 0
    assert summary.comparisons == []
    assert summary.new_count == 0


def test_turkce_karakterli_isimler(folders):
    source, target = folders
    rel = Path("çalışma_şüğıöç") / "günce_İşĞ.txt"
    _write(source / rel, "içerik şğüıöç".encode("utf-8"))
    summary = sync_engine.analyze(source, target)
    assert summary.new_count == 1

    result = sync_engine.synchronize(summary)
    copied = target / rel
    assert copied.exists()
    assert copied.read_bytes() == (source / rel).read_bytes()
    assert result.error_count == 0


def test_uzun_dosya_adi(folders):
    source, target = folders
    long_name = "u" * 120 + ".txt"
    _write(source / long_name, b"veri")
    summary = sync_engine.analyze(source, target)
    assert summary.new_count == 1
    sync_engine.synchronize(summary)
    assert (target / long_name).exists()


def test_new_ve_modified_sayilari(folders):
    source, target = folders
    _write(source / "yeni1.txt", b"a")
    _write(source / "yeni2.txt", b"b")
    _write(source / "degismis.txt", b"uzun icerik")
    _write(target / "degismis.txt", b"kisa")  # farklı boyut -> MODIFIED
    _write(source / "ayni.txt", b"sabit")
    _write(target / "ayni.txt", b"sabit")

    summary = sync_engine.analyze(source, target)
    assert summary.new_count == 2
    assert summary.modified_count == 1
    assert len(summary.pending) == 3


def test_senkronizasyon_sonrasi_icerik_ayni(folders):
    source, target = folders
    payload = bytes(range(256)) * 4  # ikili içerik
    _write(source / "alt" / "veri.bin", payload)
    summary = sync_engine.analyze(source, target)
    sync_engine.synchronize(summary)
    assert (target / "alt" / "veri.bin").read_bytes() == payload


def test_rapor_klasoru_olusturulamazsa_report_error(tmp_path):
    # Bir dosyayı klasörmüş gibi kullanmaya çalışınca mkdir başarısız olur.
    blocker = tmp_path / "engel"
    blocker.write_text("ben bir dosyayim", encoding="utf-8")
    summary = SyncSummary(
        source=tmp_path, target=tmp_path,
        comparisons=[FileComparison(Path("x.txt"), FileStatus.NEW, 1)],
    )
    with pytest.raises(report_manager.ReportError):
        report_manager.save_reports(summary, reports_dir=blocker / "altklasor")

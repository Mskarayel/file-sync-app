"""Senkronizasyon motoru: tarama, karşılaştırma ve kopyalama.

Bu modül UI'yı tanımaz (tkinter importu yoktur) ve bu yüzden bağımsız test
edilebilir. İlerleme bilgisi isteğe bağlı bir callback ile dışarı verilir;
UI bu callback'i kullanarak mesajları kendi kuyruğuna aktarır.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import constants
from .models import FileComparison, FileStatus, ProgressMessage, SyncSummary

logger = logging.getLogger(__name__)

# İlerleme callback'i; motor hiçbir zaman UI'yı doğrudan çağırmaz.
ProgressCallback = Callable[[ProgressMessage], None]


def _emit(callback: ProgressCallback | None, message: ProgressMessage) -> None:
    if callback is not None:
        callback(message)


def _iter_files(root: Path):
    """root altındaki tüm dosyaları göreli yollarıyla üretir (alt klasörler dahil)."""
    for path in root.rglob("*"):
        if path.is_file():
            yield path.relative_to(root)


def compute_hash(path: Path) -> str:
    """Dosyanın SHA-256 özetini parça parça okuyarak hesaplar."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(constants.HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files_are_equal(src_file: Path, dst_file: Path) -> bool:
    """İki dosyayı boyut → mtime → (şüpheliyse) hash zinciriyle karşılaştırır."""
    src_stat = src_file.stat()
    dst_stat = dst_file.stat()

    if src_stat.st_size != dst_stat.st_size:
        return False

    if abs(src_stat.st_mtime - dst_stat.st_mtime) <= constants.MTIME_TOLERANCE_SECONDS:
        # Boyut ve zaman aynı: aynı kabul edilir, pahalı hash'e gerek yok.
        return True

    # Boyut aynı ama zaman farklı: şüpheli durum, kesin karar için hash.
    return compute_hash(src_file) == compute_hash(dst_file)


def _compare_one(source: Path, target: Path, rel: Path) -> FileComparison:
    """Tek bir dosyayı karşılaştırır ve durumunu döndürür."""
    src_file = source / rel
    dst_file = target / rel
    try:
        size = src_file.stat().st_size
        if not dst_file.exists():
            return FileComparison(rel, FileStatus.NEW, size)
        if _files_are_equal(src_file, dst_file):
            return FileComparison(rel, FileStatus.SAME, size)
        return FileComparison(rel, FileStatus.MODIFIED, size)
    except OSError as exc:
        logger.warning("Karşılaştırma hatası %s: %s", rel, exc)
        return FileComparison(rel, FileStatus.ERROR, 0, str(exc))


def analyze(
    source: Path,
    target: Path,
    progress: ProgressCallback | None = None,
) -> SyncSummary:
    """Kaynağı tarar, her dosyayı hedefle karşılaştırır. Kopyalama yapmaz."""
    summary = SyncSummary(source=source, target=target, started_at=datetime.now())
    _emit(progress, ProgressMessage("log", text="Analiz başladı…"))

    relative_paths = list(_iter_files(source))
    total = len(relative_paths)
    _emit(progress, ProgressMessage("log", text=f"{total} dosya bulundu."))

    for index, rel in enumerate(relative_paths, start=1):
        comparison = _compare_one(source, target, rel)
        summary.comparisons.append(comparison)
        _emit(
            progress,
            ProgressMessage("progress", current=index, total=total, text=str(rel)),
        )

    summary.finished_at = datetime.now()
    _emit(progress, ProgressMessage("done", payload=summary, text="Analiz tamamlandı."))
    return summary


def synchronize(
    plan: SyncSummary,
    progress: ProgressCallback | None = None,
) -> SyncSummary:
    """Analiz sonucundaki yeni/değişmiş dosyaları kopyalar.

    Bir dosyadaki hata tüm işlemi durdurmaz; hatalı dosyalar sonuç özetine
    ERROR olarak eklenir. Aynı ve zaten hatalı dosyalar olduğu gibi taşınır.
    """
    source, target = plan.source, plan.target
    result = SyncSummary(source=source, target=target, started_at=datetime.now())

    pending = plan.pending
    total = len(pending)
    _emit(progress, ProgressMessage("log", text=f"{total} dosya işlenecek."))

    # Kopyalanmayacak dosyaları (SAME / önceki ERROR) sonuca aynen taşı.
    for comparison in plan.comparisons:
        if comparison.status not in (FileStatus.NEW, FileStatus.MODIFIED):
            result.comparisons.append(comparison)

    for index, comparison in enumerate(pending, start=1):
        rel = comparison.relative_path
        original_status = comparison.status
        outcome = _copy_one(source, target, rel, original_status)
        result.comparisons.append(outcome)

        if outcome.status is FileStatus.ERROR:
            _emit(progress, ProgressMessage("log", text=f"HATA: {rel} → {outcome.error_message}"))
        else:
            _emit(progress, ProgressMessage("log", text=f"Kopyalandı: {rel}"))
        _emit(
            progress,
            ProgressMessage("progress", current=index, total=total, text=str(rel)),
        )

    result.finished_at = datetime.now()
    _emit(progress, ProgressMessage("done", payload=result, text="Senkronizasyon tamamlandı."))
    return result


def _copy_one(
    source: Path, target: Path, rel: Path, original_status: FileStatus
) -> FileComparison:
    """Tek bir dosyayı kopyalar; hata olursa ERROR döndürür (istisna atmaz)."""
    src_file = source / rel
    dst_file = target / rel
    try:
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)  # copy2 zaman bilgisini korur.
        return FileComparison(rel, original_status, dst_file.stat().st_size)
    except OSError as exc:
        logger.warning("Kopyalama hatası %s: %s", rel, exc)
        return FileComparison(rel, FileStatus.ERROR, 0, str(exc))

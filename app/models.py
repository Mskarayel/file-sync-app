"""Veri modelleri.

Bu modül yalnızca standart kütüphaneye bağımlıdır; UI veya senkronizasyon
motoruna bağımlı değildir. Böylece her katman aynı veri tiplerini paylaşır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class FileStatus(Enum):
    """Bir dosyanın kaynak/hedef karşılaştırmasındaki durumu."""

    NEW = "new"            # Hedefte yok, kopyalanacak.
    MODIFIED = "modified"  # İçerik/boyut/zaman farklı, güncellenecek.
    SAME = "same"          # Aynı, atlanacak.
    ERROR = "error"        # Erişilemedi veya kopyalanamadı.


# UI'da gösterilecek Türkçe etiketler.
STATUS_LABELS: dict[FileStatus, str] = {
    FileStatus.NEW: "Yeni",
    FileStatus.MODIFIED: "Değişmiş",
    FileStatus.SAME: "Aynı",
    FileStatus.ERROR: "Hata",
}


@dataclass
class FileComparison:
    """Tek bir dosyanın karşılaştırma sonucu.

    relative_path kaynağa göre göreli yoldur; alt klasör yapısı bu alan
    sayesinde hedefte birebir korunur.
    """

    relative_path: Path
    status: FileStatus
    size: int = 0
    error_message: str | None = None


@dataclass
class SyncSummary:
    """Bir analiz veya senkronizasyon işleminin toplu sonucu."""

    source: Path
    target: Path
    comparisons: list[FileComparison] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    def _count(self, status: FileStatus) -> int:
        return sum(1 for c in self.comparisons if c.status is status)

    @property
    def new_count(self) -> int:
        return self._count(FileStatus.NEW)

    @property
    def modified_count(self) -> int:
        return self._count(FileStatus.MODIFIED)

    @property
    def same_count(self) -> int:
        return self._count(FileStatus.SAME)

    @property
    def error_count(self) -> int:
        return self._count(FileStatus.ERROR)

    @property
    def duration_seconds(self) -> float:
        """Başlangıç ile bitiş arasındaki toplam süre (saniye)."""
        end = self.finished_at or datetime.now()
        return max(0.0, (end - self.started_at).total_seconds())

    @property
    def total_count(self) -> int:
        return len(self.comparisons)

    @property
    def pending(self) -> list[FileComparison]:
        """Kopyalanması/güncellenmesi gereken dosyalar."""
        return [
            c
            for c in self.comparisons
            if c.status in (FileStatus.NEW, FileStatus.MODIFIED)
        ]


@dataclass
class ProgressMessage:
    """Worker thread'den UI'ya kuyruk üzerinden aktarılan mesaj.

    kind: "progress" | "log" | "done" | "error"
    payload genellikle bir SyncSummary taşır ("done" mesajında).
    """

    kind: str
    current: int = 0
    total: int = 0
    text: str = ""
    payload: object = None

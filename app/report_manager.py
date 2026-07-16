"""Senkronizasyon raporlarını TXT ve JSON olarak üretir.

UI'yı tanımaz. Bir SyncSummary alır, reports/ klasörüne zaman damgalı
dosyalar yazar ve oluşturulan yolları döndürür.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from . import constants
from .models import STATUS_LABELS, SyncSummary

logger = logging.getLogger(__name__)


class ReportError(Exception):
    """Rapor yazılırken oluşan hataları temsil eder."""


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def build_report_dict(summary: SyncSummary) -> dict:
    """SyncSummary'yi JSON'a uygun bir sözlüğe dönüştürür."""
    return {
        "source": str(summary.source),
        "target": str(summary.target),
        "started_at": _format_datetime(summary.started_at),
        "finished_at": _format_datetime(summary.finished_at),
        "duration_seconds": round(summary.duration_seconds, 3),
        "totals": {
            "total": summary.total_count,
            "new": summary.new_count,
            "modified": summary.modified_count,
            "same": summary.same_count,
            "error": summary.error_count,
        },
        "files": [
            {
                "relative_path": str(c.relative_path),
                "status": c.status.value,
                "size": c.size,
                "error_message": c.error_message,
            }
            for c in summary.comparisons
        ],
    }


def render_text_report(summary: SyncSummary) -> str:
    """İnsan tarafından okunabilir TXT rapor metni üretir."""
    lines: list[str] = [
        f"{constants.APP_NAME} — Senkronizasyon Raporu",
        "=" * 50,
        f"Kaynak klasör : {summary.source}",
        f"Hedef klasör  : {summary.target}",
        f"Başlangıç     : {_format_datetime(summary.started_at)}",
        f"Bitiş         : {_format_datetime(summary.finished_at)}",
        f"Toplam süre   : {summary.duration_seconds:.2f} sn",
        "",
        f"Toplam dosya  : {summary.total_count}",
        f"  Yeni        : {summary.new_count}",
        f"  Değişmiş    : {summary.modified_count}",
        f"  Aynı        : {summary.same_count}",
        f"  Hatalı      : {summary.error_count}",
        "",
        "Dosya Ayrıntıları",
        "-" * 50,
    ]
    for c in summary.comparisons:
        line = f"[{STATUS_LABELS[c.status]:<9}] {c.relative_path} ({c.size} B)"
        if c.error_message:
            line += f" — HATA: {c.error_message}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _build_filename(prefix: str, extension: str, timestamp: datetime) -> str:
    stamp = timestamp.strftime(constants.TIMESTAMP_FORMAT)
    return f"{prefix}_{stamp}.{extension}"


def save_reports(
    summary: SyncSummary,
    reports_dir: Path | None = None,
    formats: tuple[str, ...] | list[str] = constants.REPORT_FORMAT_OPTIONS,
    timestamp: datetime | None = None,
) -> dict[str, Path]:
    """Raporları istenen formatlarda diske yazar ve yolları döndürür.

    Yazma hatalarını ReportError olarak yükseltir; böylece çağıran katman
    kullanıcıya anlaşılır mesaj gösterebilir.
    """
    reports_dir = reports_dir or constants.REPORTS_DIR
    timestamp = timestamp or datetime.now()
    prefix = constants.REPORT_FILENAME_PREFIX
    written: dict[str, Path] = {}

    try:
        reports_dir.mkdir(parents=True, exist_ok=True)

        if "txt" in formats:
            txt_path = reports_dir / _build_filename(prefix, "txt", timestamp)
            txt_path.write_text(render_text_report(summary), encoding="utf-8")
            written["txt"] = txt_path

        if "json" in formats:
            json_path = reports_dir / _build_filename(prefix, "json", timestamp)
            data = build_report_dict(summary)
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written["json"] = json_path
    except OSError as exc:
        logger.error("Rapor yazılamadı: %s", exc)
        raise ReportError(f"Rapor yazılamadı: {exc}") from exc

    return written

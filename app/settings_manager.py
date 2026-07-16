"""Uygulama ayarlarını JSON dosyasında saklar ve yükler.

Son kullanılan klasörler, tema tercihi ve rapor formatı tercihleri tutulur.
Dosya yoksa veya bozuksa varsayılan ayarlara güvenli şekilde geri dönülür.
"""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path

from . import constants

logger = logging.getLogger(__name__)


def default_settings() -> dict:
    """Varsayılan ayarların yeni bir kopyasını döndürür."""
    settings = dict(constants.DEFAULT_SETTINGS)
    # İç içe listeler için de kopya al ki paylaşılan referans olmasın.
    settings["recent_sources"] = list(constants.DEFAULT_SETTINGS["recent_sources"])
    settings["recent_targets"] = list(constants.DEFAULT_SETTINGS["recent_targets"])
    settings["report_formats"] = list(constants.DEFAULT_SETTINGS["report_formats"])
    return settings


def _json_default(value: object) -> str:
    """Path ve Enum gibi nesneleri JSON'a uygun biçime çevirir."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"JSON'a çevrilemeyen tip: {type(value)!r}")


def load_settings(path: Path | None = None) -> dict:
    """Ayarları yükler. Dosya yoksa veya bozuksa varsayılanları döndürür."""
    path = path or constants.SETTINGS_FILE
    if not path.exists():
        return default_settings()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Ayar dosyası okunamadı, varsayılanlara dönülüyor: %s", exc)
        return default_settings()

    if not isinstance(raw, dict):
        logger.warning("Ayar dosyası beklenen biçimde değil, varsayılanlara dönülüyor.")
        return default_settings()

    # Eksik anahtarları varsayılanlarla tamamla (ileri/geri uyumluluk).
    settings = default_settings()
    settings.update({k: v for k, v in raw.items() if k in settings})
    return settings


def save_settings(settings: dict, path: Path | None = None) -> None:
    """Ayarları atomik biçimde kaydeder (önce geçici dosya, sonra yer değiştir)."""
    path = path or constants.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")

    try:
        tmp_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)  # Aynı dizinde atomik yer değiştirme.
    except OSError as exc:
        logger.error("Ayarlar kaydedilemedi: %s", exc)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def add_recent_folder(
    settings: dict,
    key: str,
    folder: str | Path,
    max_items: int = constants.MAX_RECENT_FOLDERS,
) -> dict:
    """Bir klasörü son kullanılanların başına ekler (tekrarları temizler)."""
    folder = str(folder)
    recent = [f for f in settings.get(key, []) if f != folder]
    recent.insert(0, folder)
    settings[key] = recent[:max_items]
    return settings

"""Uygulama genelinde kullanılan sabitler.

Global değişken yerine tek bir sabit modülü kullanılır. UI ve motor
katmanları bu sabitleri paylaşır.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "Dosya Senkronizasyon Aracı"
APP_VERSION = "1.0.0"

# Hash hesaplarken dosya parça parça okunur (büyük dosyalarda bellek dostu).
HASH_CHUNK_SIZE = 64 * 1024

# mtime karşılaştırmasında tolerans (saniye). OneDrive / FAT gibi dosya
# sistemleri zaman damgasını saniye altı hassasiyette tutamayabilir.
MTIME_TOLERANCE_SECONDS = 2.0

# Uygulama kök dizini (file_sync_app/).
BASE_DIR = Path(__file__).resolve().parent.parent

LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
SETTINGS_FILE = BASE_DIR / "settings.json"

# Son kullanılan klasörlerden kaç tanesi hatırlanacak.
MAX_RECENT_FOLDERS = 5

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

# Teknik uygulama günlüğü (kullanıcıya gösterilen işlem günlüğünden ayrıdır).
LOG_FILE = LOGS_DIR / "app.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

# Son kullanılan klasörlerden kaç tanesi hatırlanacak.
MAX_RECENT_FOLDERS = 5

# Rapor dosyalarının ön eki ve tarih-saat biçimi.
REPORT_FILENAME_PREFIX = "sync_report"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Geçerli tema seçenekleri ve rapor formatları.
THEME_OPTIONS = ("System", "Light", "Dark")
REPORT_FORMAT_OPTIONS = ("txt", "json")

# Ayar dosyası yoksa kullanılacak varsayılanlar.
DEFAULT_SETTINGS: dict = {
    "theme": "System",
    "last_source": "",
    "last_target": "",
    "recent_sources": [],
    "recent_targets": [],
    "report_formats": ["txt", "json"],
}

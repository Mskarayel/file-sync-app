"""Ayar yönetimi testleri (UI'sız, tmp_path ile)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import settings_manager  # noqa: E402


def test_dosya_yoksa_varsayilanlar(tmp_path):
    settings = settings_manager.load_settings(tmp_path / "yok.json")
    assert settings["theme"] == "System"
    assert settings["recent_sources"] == []


def test_kaydet_ve_yukle_donusumu(tmp_path):
    path = tmp_path / "settings.json"
    settings = settings_manager.default_settings()
    settings["theme"] = "Dark"
    settings["last_source"] = "C:/veri/kaynak"
    settings_manager.save_settings(settings, path)

    loaded = settings_manager.load_settings(path)
    assert loaded["theme"] == "Dark"
    assert loaded["last_source"] == "C:/veri/kaynak"


def test_bozuk_json_varsayilana_doner(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ bu gecerli json degil ]", encoding="utf-8")
    settings = settings_manager.load_settings(path)
    assert settings == settings_manager.default_settings()


def test_path_ve_enum_serilestirilebilir(tmp_path):
    from enum import Enum

    class Theme(Enum):
        DARK = "Dark"

    path = tmp_path / "settings.json"
    settings = settings_manager.default_settings()
    settings["last_source"] = Path("C:/veri/kaynak")  # Path nesnesi
    settings["theme"] = Theme.DARK  # Enum nesnesi
    settings_manager.save_settings(settings, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["last_source"] == "C:\\veri\\kaynak" or raw["last_source"] == "C:/veri/kaynak"
    assert raw["theme"] == "Dark"


def test_atomik_kayit_gecici_dosya_birakmaz(tmp_path):
    path = tmp_path / "settings.json"
    settings_manager.save_settings(settings_manager.default_settings(), path)
    assert path.exists()
    assert not (tmp_path / "settings.json.tmp").exists()


def test_son_klasor_ekleme_ve_sinir(tmp_path):
    settings = settings_manager.default_settings()
    for i in range(7):
        settings_manager.add_recent_folder(settings, "recent_sources", f"klasor_{i}", max_items=5)
    assert len(settings["recent_sources"]) == 5
    assert settings["recent_sources"][0] == "klasor_6"  # En son eklenen başta.


def test_son_klasor_tekrar_temizlenir(tmp_path):
    settings = settings_manager.default_settings()
    settings_manager.add_recent_folder(settings, "recent_targets", "ayni", max_items=5)
    settings_manager.add_recent_folder(settings, "recent_targets", "baska", max_items=5)
    settings_manager.add_recent_folder(settings, "recent_targets", "ayni", max_items=5)
    assert settings["recent_targets"] == ["ayni", "baska"]

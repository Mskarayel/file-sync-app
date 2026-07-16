"""Kaynak ve hedef klasör güvenlik doğrulamaları.

Saf fonksiyonlardır; dosya sistemi dışında bağımlılıkları yoktur ve UI'yı
tanımazlar. Bu sayede bağımsız test edilebilirler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    ok: bool
    message: str = ""


def _is_relative_to(path: Path, other: Path) -> bool:
    """path, other'ın altında mı? (Python 3.9+ uyumlu yardımcı.)"""
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def validate_folders(source: Path, target: Path) -> ValidationResult:
    """Kaynak/hedef klasör çiftini senkronizasyon için doğrular."""
    if not source.exists():
        return ValidationResult(False, "Kaynak klasör bulunamadı.")
    if not source.is_dir():
        return ValidationResult(False, "Kaynak bir klasör olmalı.")
    if not target.exists():
        return ValidationResult(False, "Hedef klasör bulunamadı.")
    if not target.is_dir():
        return ValidationResult(False, "Hedef bir klasör olmalı.")

    # Sembolik bağları ve '..' gibi yolları çözerek karşılaştır.
    src = source.resolve()
    dst = target.resolve()

    if src == dst:
        return ValidationResult(False, "Kaynak ve hedef klasör aynı olamaz.")
    if _is_relative_to(dst, src):
        return ValidationResult(
            False, "Hedef klasör, kaynak klasörün altında olamaz."
        )
    if _is_relative_to(src, dst):
        return ValidationResult(
            False, "Kaynak klasör, hedef klasörün altında olamaz."
        )

    return ValidationResult(True)

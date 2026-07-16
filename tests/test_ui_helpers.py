"""UI'daki saf yardımcı fonksiyonların testleri (pencere açmadan)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ui  # noqa: E402  (import sırasında pencere açılmaz)


def test_format_size_byte():
    assert ui.format_size(0) == "0 B"
    assert ui.format_size(512) == "512 B"


def test_format_size_kb_mb():
    assert ui.format_size(1536) == "1.5 KB"
    assert ui.format_size(1048576) == "1.0 MB"
    assert ui.format_size(1073741824) == "1.0 GB"


def test_display_path_bos():
    assert ui.display_path("") == ""


def test_display_path_normalize():
    # str(Path(...)) işletim sistemine uygun ayraç verir; ayraç sayısı korunur.
    result = ui.display_path("a/b/c")
    assert "a" in result and "b" in result and "c" in result
    assert "/" not in result if sys.platform.startswith("win") else True

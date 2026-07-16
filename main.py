"""Uygulama giriş noktası."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from app.ui import FileSyncApp


def resource_path(relative_path: str) -> Path:
    """Geliştirme ve PyInstaller ortamında kaynak dosyanın yolunu döndürür."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def main() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "Mskarayel.FileSync.1.0"
    )

    app = FileSyncApp()
    app.iconbitmap(str(resource_path("assets/icon.ico")))
    app.mainloop()


if __name__ == "__main__":
    main()
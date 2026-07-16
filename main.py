"""Uygulama giriş noktası."""

from __future__ import annotations

import ctypes

from app.ui import FileSyncApp


def main() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "Mskarayel.FileSync.1.0"
    )

    app = FileSyncApp()
    app.iconbitmap("assets/icon.ico")
    app.mainloop()


if __name__ == "__main__":
    main()
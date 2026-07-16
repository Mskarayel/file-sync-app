"""Uygulama giriş noktası."""

from __future__ import annotations

from app.ui import FileSyncApp


def main() -> None:
    app = FileSyncApp()
    app.mainloop()


if __name__ == "__main__":
    main()

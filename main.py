"""Uygulama giriş noktası.

Aşama 1-4 kapsamında UI henüz eklenmedi; şimdilik motorun bağımsız
çalıştığını doğrulayan bir uyarı gösterir. UI aşamasında burada App
başlatılacaktır.
"""

from __future__ import annotations


def main() -> None:
    print("Dosya Senkronizasyon Aracı — motor katmanı hazır.")
    print("Testler için: python -m pytest file_sync_app/tests")


if __name__ == "__main__":
    main()

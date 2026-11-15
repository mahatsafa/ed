"""Alur utama bot.

Mode biasa  : python bot.py --target mock --headed
Mode attach : python bot.py --target real --attach http://127.0.0.1:9222
  (bot menempel ke Chrome yang Anda buka sendiri; verifikasi dan login Anda lakukan manual)
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from helpers import setup_logger
from login import login
from tugas import jalankan_semua

URLS = {
    "mock": (Path(__file__).parent / "mock.html").resolve().as_uri(),
    "real": "https://ed.engdis.com",
}
CIRI_HALAMAN = {"mock": "mock.html", "real": "ed.engdis.com"}  # untuk mencari tab di mode attach


def load_credentials():
    """Baca data login dari .env. Kosong = berhenti (gagal tertutup)."""
    load_dotenv()
    user = os.getenv("ENGDIS_USER", "").strip()
    password = os.getenv("ENGDIS_PASS", "")
    if not user or not password:
        raise SystemExit("ENGDIS_USER / ENGDIS_PASS di .env masih kosong.")
    return user, password


def cari_tab(browser, target):
    """Cari tab yang sudah Anda buka untuk target ini. Tidak ketemu = berhenti."""
    for context in browser.contexts:
        for page in context.pages:
            if CIRI_HALAMAN[target] in page.url:
                return page
    raise RuntimeError(f"Tab '{CIRI_HALAMAN[target]}' tidak ditemukan di browser itu.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["mock", "real"], default="mock")
    parser.add_argument("--headed", action="store_true", help="tampilkan jendela browser")
    parser.add_argument("--attach", metavar="URL_CDP",
                        help="tempel ke browser yang sudah terbuka, mis. http://127.0.0.1:9222")
    args = parser.parse_args()

    log = setup_logger()
    log.info("Mulai bot, target=%s, attach=%s", args.target, bool(args.attach))

    with sync_playwright() as pw:
        if args.attach:
            # Anda sudah login sendiri; bot hanya mengerjakan tugas di tab itu.
            browser = pw.chromium.connect_over_cdp(args.attach)
            page = cari_tab(browser, args.target)
            jalankan_semua(page)
        else:
            user, password = load_credentials()
            browser = pw.chromium.launch(headless=not args.headed)
            page = browser.new_page()
            try:
                login(page, args.target, URLS[args.target], user, password)
                jalankan_semua(page)
            finally:
                browser.close()
    log.info("Selesai.")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        setup_logger().error("Bot berhenti: %s", err)
        sys.exit(1)

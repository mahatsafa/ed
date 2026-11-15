"""Alur utama bot. Contoh: python bot.py --target mock --headed"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from helpers import setup_logger
from login import login

URLS = {
    "mock": (Path(__file__).parent / "mock.html").resolve().as_uri(),
    "real": "https://ed.engdis.com",
}


def load_credentials():
    """Baca data login dari .env. Kosong = berhenti (gagal tertutup)."""
    load_dotenv()
    user = os.getenv("ENGDIS_USER", "").strip()
    password = os.getenv("ENGDIS_PASS", "")
    if not user or not password:
        raise SystemExit("ENGDIS_USER / ENGDIS_PASS di .env masih kosong.")
    return user, password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["mock", "real"], default="mock")
    parser.add_argument("--headed", action="store_true", help="tampilkan jendela browser")
    args = parser.parse_args()

    log = setup_logger()
    user, password = load_credentials()
    log.info("Mulai bot, target=%s", args.target)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        try:
            login(page, args.target, URLS[args.target], user, password)
            # Tahap berikutnya: video, jawaban, huruf kosong, teks, mikrofon, start, header.
        finally:
            browser.close()
    log.info("Selesai.")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        setup_logger().error("Bot berhenti: %s", err)
        sys.exit(1)

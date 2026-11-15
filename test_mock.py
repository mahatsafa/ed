"""Uji otomatis login di mock.html. Jalankan: python test_mock.py"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from bot import URLS, load_credentials
from helpers import LOG_DIR
from login import login

failures = []


def check(name, ok):
    print(("LULUS  " if ok else "GAGAL  ") + name)
    if not ok:
        failures.append(name)


user, password = load_credentials()
LOG_DIR.mkdir(exist_ok=True)
before = set(LOG_DIR.glob("*.png"))

with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # 1. Login normal berhasil.
    page = browser.new_page()
    try:
        login(page, "mock", URLS["mock"], user, password)
        check("login normal -> dashboard terlihat", page.locator("#dashboard").is_visible())
    except Exception as err:
        check(f"login normal ({err})", False)
    page.close()

    # 2. Password kosong harus gagal dan menyimpan screenshot.
    page = browser.new_page()
    try:
        login(page, "mock", URLS["mock"], user, "", timeout=1500)
        check("password kosong harus gagal", False)
    except Exception:
        check("password kosong -> login gagal", True)
    page.close()
    browser.close()

# 3. Screenshot kegagalan tersimpan.
new_png = set(LOG_DIR.glob("*.png")) - before
check("screenshot kegagalan tersimpan di logs/", len(new_png) >= 1)

# 4. Password tidak bocor ke log.
log_text = (LOG_DIR / "bot.log").read_text()
check("password tidak ada di logs/bot.log", password not in log_text)

# 5. Target 'real' berhenti karena selector belum diisi.
try:
    login(None, "real", URLS["real"], user, password)
    check("target real tanpa selector harus ditolak", False)
except RuntimeError:
    check("target real tanpa selector -> ditolak", True)

sys.exit(1 if failures else 0)

"""Alur utama bot.

Mode biasa  : python bot.py --target mock --headed
Mode attach : python bot.py --target real --attach http://127.0.0.1:9222
  (bot menempel ke Chrome yang Anda buka sendiri; verifikasi dan login Anda lakukan manual)
Mode buka   : python bot.py --target real --buka
  (bot membuka Chromium di WSL dengan port debug, Anda login manual lalu tekan Enter, bot mengerjakan)
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from helpers import setup_logger
from login import login
from pelajaran import jalankan_pelajaran
from tugas import jalankan_semua

URLS = {
    "mock": (Path(__file__).parent / "mock.html").resolve().as_uri(),
    "real": "https://ed.engdis.com",
}
CIRI_HALAMAN = {"mock": "mock.html", "real": "ed.engdis.com"}  # untuk mencari tab di mode attach
PORT_CDP = 9222
PROFIL_CHROME = Path.home() / ".engdis-chrome-profil"  # di luar repo; sesi login tersimpan di sini
CHROME_CADANGAN = ("/usr/bin/google-chrome", "/usr/bin/chromium-browser")  # kalau Chromium Playwright tak ada
MAKS_TUNGGU_CHROME = 80  # x 0,25 detik = 20 detik menunggu port debug siap


def load_credentials():
    """Baca data login dari .env. Kosong = berhenti (gagal tertutup)."""
    load_dotenv()
    user = os.getenv("ENGDIS_USER", "").strip()
    password = os.getenv("ENGDIS_PASS", "")
    if not user or not password:
        raise SystemExit("ENGDIS_USER / ENGDIS_PASS di .env masih kosong.")
    return user, password


def cdp_siap(port):
    """True kalau ada browser yang menjawab di port debug."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1):
            return True
    except OSError:
        return False


def buka_chrome(pw, url, port=PORT_CDP, tanpa_jendela=False, profil=PROFIL_CHROME):
    """Buka Chromium sebagai proses biasa dengan port debug (login tetap manual). Kembalikan prosesnya,
    atau None kalau port itu sudah dipakai browser lain (dipakai ulang, tidak dibuka dobel)."""
    log = setup_logger()
    if cdp_siap(port):
        log.info("Port %d sudah ada browser; dipakai ulang, tidak membuka baru.", port)
        return None
    exe = next((p for p in (pw.chromium.executable_path, *CHROME_CADANGAN) if os.path.exists(p)), None)
    if exe is None:
        raise RuntimeError("Chromium tidak ditemukan. Jalankan: .venv/bin/python -m playwright install chromium")
    profil.mkdir(parents=True, exist_ok=True)
    perintah = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profil}", "--no-first-run", url]
    if tanpa_jendela:  # hanya untuk uji otomatis
        perintah.insert(1, "--headless=new")
    log.info("Membuka Chromium: %s", exe)
    proses = subprocess.Popen(perintah, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(MAKS_TUNGGU_CHROME):  # batas atas menunggu
        if cdp_siap(port):
            return proses
        if proses.poll() is not None:
            raise RuntimeError(f"Chromium langsung berhenti (kode {proses.returncode}).")
        time.sleep(0.25)
    proses.terminate()
    raise RuntimeError(f"Port debug {port} tidak siap dalam {MAKS_TUNGGU_CHROME // 4} detik.")


def jalankan(page, target):
    """Situs asli: pengulang pelajaran. Mock: semua elemen dalam satu halaman."""
    if target == "real":
        return jalankan_pelajaran(page)
    return jalankan_semua(page)


def cari_tab(browser, target):
    """Cari tab yang sudah Anda buka untuk target ini. Tidak ketemu = berhenti."""
    kandidat, terlihat = [], []
    for context in browser.contexts:
        for page in context.pages:
            terlihat.append(page.url.split("?")[0])
            if CIRI_HALAMAN[target] in page.url and "error.html" not in page.url:
                kandidat.append(page)
    for page in kandidat:  # utamakan tab yang sedang tampil di layar
        if page.evaluate("document.visibilityState") == "visible":
            return page
    if kandidat:
        return kandidat[-1]
    raise RuntimeError(
        f"Tab '{CIRI_HALAMAN[target]}' tidak ditemukan. Tab yang terlihat bot: "
        f"{terlihat or 'tidak ada'}. Buka dan login di jendela Chrome dari blok 2, "
        "bukan di Chrome biasa.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["mock", "real"], default="mock")
    parser.add_argument("--headed", action="store_true", help="tampilkan jendela browser")
    parser.add_argument("--attach", metavar="URL_CDP",
                        help="tempel ke browser yang sudah terbuka, mis. http://127.0.0.1:9222")
    parser.add_argument("--buka", action="store_true",
                        help="buka Chromium di WSL sendiri, tunggu Anda login, lalu kerjakan (memakai --attach otomatis)")
    args = parser.parse_args()
    if args.buka:
        if args.attach:
            parser.error("--buka dan --attach tidak boleh dipakai bersamaan.")
        args.attach = f"http://127.0.0.1:{PORT_CDP}"

    log = setup_logger()
    log.info("Mulai bot, target=%s, attach=%s", args.target, bool(args.attach))

    with sync_playwright() as pw:
        if args.buka:
            buka_chrome(pw, URLS[args.target])
            input("Login dan selesaikan verifikasi di jendela Chromium, buka dashboard, lalu tekan Enter di sini... ")
        if args.attach:
            # Anda sudah login sendiri; bot hanya mengerjakan tugas di tab itu.
            browser = pw.chromium.connect_over_cdp(args.attach)
            page = cari_tab(browser, args.target)
            jalankan(page, args.target)
        else:
            user, password = load_credentials()
            browser = pw.chromium.launch(headless=not args.headed)
            page = browser.new_page()
            try:
                login(page, args.target, URLS[args.target], user, password)
                jalankan(page, args.target)
            finally:
                browser.close()
    log.info("Selesai.")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        setup_logger().error("Bot berhenti: %s", err)
        sys.exit(1)

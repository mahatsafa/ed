"""Fungsi kecil yang dipakai bersama: log, tunggu elemen, klik, screenshot."""
import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
TIMEOUT_MS = 10_000  # batas tunggu elemen; lewat dari ini dianggap gagal


def setup_logger():
    """Buat logger yang menulis ke layar dan ke logs/bot.log."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("bot")
    if logger.handlers:  # jangan dobel kalau dipanggil dua kali
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "bot.log")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def screenshot_on_fail(page, name):
    """Simpan screenshot ke logs/ dengan nama waktu_nama.png."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = LOG_DIR / f"{stamp}_{name}.png"
    try:
        page.screenshot(path=str(path))
        setup_logger().error("Screenshot kegagalan: %s", path)
    except Exception as err:  # screenshot gagal tidak boleh menutupi error asli
        setup_logger().error("Screenshot gagal disimpan: %s", err)
    return path


def periksa(page, name, check):
    """Jalankan pemeriksaan (expect). Gagal -> log, screenshot, lempar ulang error."""
    log = setup_logger()
    try:
        check()
    except Exception:
        log.error("Pemeriksaan gagal: %s", name)
        screenshot_on_fail(page, f"periksa_{name}")
        raise
    log.info("OK: %s", name)


def wait_visible(page, locator, name, timeout=TIMEOUT_MS):
    """Tunggu sampai elemen terlihat. Gagal -> log, screenshot, lempar ulang error."""
    log = setup_logger()
    log.info("Menunggu: %s", name)
    try:
        locator.wait_for(state="visible", timeout=timeout)
    except Exception:
        log.error("Elemen tidak muncul: %s", name)
        screenshot_on_fail(page, f"tunggu_{name}")
        raise
    return locator


def click(page, locator, name, timeout=TIMEOUT_MS):
    """Klik elemen. Playwright otomatis menunggu elemen siap diklik."""
    log = setup_logger()
    log.info("Klik: %s", name)
    try:
        locator.click(timeout=timeout)
    except Exception:
        log.error("Gagal klik: %s", name)
        screenshot_on_fail(page, f"klik_{name}")
        raise

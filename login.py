"""Fungsi login. Selector per target disimpan di SELECTORS di bawah."""
from helpers import click, screenshot_on_fail, setup_logger, wait_visible

# Selector tiap target. Nilai None = belum diisi (menunggu HTML dari Bima).
SELECTORS = {
    "mock": {
        "username": "#username",
        "password": "#password",
        "submit": "#btn-login",
        "after_login": "#dashboard",  # hanya terlihat setelah login
    },
    "real": {
        "username": None,
        "password": None,
        "submit": None,
        "after_login": None,
    },
}


def mask(text):
    """Samarkan username di log: 542251110 -> 54*****10."""
    if len(text) <= 4:
        return "****"
    return text[:2] + "*" * (len(text) - 4) + text[-2:]


def login(page, target, url, user, password, timeout=10_000):
    """Buka halaman login, isi form, klik masuk, tunggu elemen pasca-login."""
    log = setup_logger()
    sel = SELECTORS[target]
    if not all(sel.values()):  # gagal tertutup: jangan menebak selector
        raise RuntimeError(f"Selector target '{target}' belum diisi lengkap.")

    log.info("Buka halaman login: %s", url)
    page.goto(url)

    wait_visible(page, page.locator(sel["username"]), "isian_username", timeout)
    log.info("Isi username: %s", mask(user))
    page.locator(sel["username"]).fill(user)
    log.info("Isi password: (disembunyikan)")
    page.locator(sel["password"]).fill(password)

    click(page, page.locator(sel["submit"]), "tombol_masuk", timeout)

    try:
        wait_visible(page, page.locator(sel["after_login"]), "halaman_setelah_login", timeout)
    except Exception:
        screenshot_on_fail(page, "login_gagal")
        log.error("Login gagal: elemen pasca-login tidak muncul.")
        raise
    log.info("Login berhasil.")

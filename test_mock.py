"""Uji otomatis di mock.html. Jalankan: python test_mock.py"""
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from bot import URLS, load_credentials
from helpers import LOG_DIR
from login import login
import pelajaran
import tugas

BASE = Path(__file__).parent
PORT_CDP = 9333  # port uji untuk mode attach
failures = []


def check(name, ok):
    print(("LULUS  " if ok else "GAGAL  ") + name)
    if not ok:
        failures.append(name)


def raises(fn, *exc):
    try:
        fn()
    except exc or Exception:
        return True
    return False


def halaman_login(browser, user, password):
    page = browser.new_page()
    login(page, "mock", URLS["mock"], user, password)
    return page


user, password = load_credentials()
LOG_DIR.mkdir(exist_ok=True)
before = set(LOG_DIR.glob("*.png"))

with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # --- Login ---
    page = browser.new_page()
    try:
        login(page, "mock", URLS["mock"], user, password)
        check("login normal -> dashboard terlihat", page.locator("#dashboard").is_visible())
    except Exception as err:
        check(f"login normal ({err})", False)
    page.close()

    page = browser.new_page()
    check("password kosong -> login gagal",
          raises(lambda: login(page, "mock", URLS["mock"], user, "", timeout=1500)))
    page.close()

    # --- Fungsi per elemen (halaman baru tiap uji) ---
    page = halaman_login(browser, user, password)
    tugas.putar_video(page)
    check("video terputar (tidak paused, waktu maju)", page.evaluate(
        "() => { const v = document.querySelector('#video');"
        " return !v.paused && v.currentTime > 0; }"))
    page.close()

    page = halaman_login(browser, user, password)
    tugas.pilih_jawaban(page, "b")
    check("jawaban terpilih + Completed task + tanpa reminder",
          page.locator("#completed").is_visible() and not page.locator("#reminder").is_visible()
          and page.locator("input[value=b]").is_checked())
    page.close()

    page = halaman_login(browser, user, password)
    page.locator("#btn-submit").click()  # submit tanpa memilih: mock harus memberi reminder
    check("mock: submit tanpa pilih -> reminder, tanpa Completed",
          page.locator("#reminder").is_visible() and not page.locator("#completed").is_visible())
    page.close()

    page = halaman_login(browser, user, password)
    check("pilihan jawaban tidak ada -> gagal",
          raises(lambda: tugas.pilih_jawaban(page, "z", timeout=1500)))
    page.close()

    page = halaman_login(browser, user, password)
    tugas.isi_huruf_kosong(page)
    check("semua kotak huruf terisi", page.evaluate(
        "() => [...document.querySelectorAll('.blank')].every(b => b.textContent)"))
    page.close()

    page = halaman_login(browser, user, password)
    tugas.isi_teks(page)
    check("kolom teks = teks pertanyaan",
          page.locator("#text-answer").input_value() == "What is your name?")
    page.close()

    page = halaman_login(browser, user, password)
    tugas.klik_mikrofon(page)
    check("mikrofon diklik", page.locator("#mic-status").inner_text() == "mikrofon diklik")
    page.close()

    page = halaman_login(browser, user, password)
    tugas.klik_start(page)
    check("Start aktif dan dimulai", page.locator("#start-status").inner_text() == "sudah dimulai")
    page.close()

    page = halaman_login(browser, user, password)
    tugas.klik_header(page)
    check("dua tombol header diklik", page.locator("#header-status").inner_text() == "header 2 diklik")
    page.close()

    page = halaman_login(browser, user, password)
    page.evaluate("() => document.querySelector('#word-bank').remove()")
    check("tanpa pilihan kata -> berhenti (gagal tertutup)",
          raises(lambda: tugas.isi_huruf_kosong(page), RuntimeError))
    page.close()

    page = halaman_login(browser, user, password)
    tugas.jalankan_semua(page)
    check("jalankan_semua berurutan sampai selesai", page.locator("#header-status").inner_text() == "header 2 diklik")
    page.close()

    # --- Pengulang pelajaran (halaman tiruan dengan selector situs asli) ---
    URL_ASLI = (BASE / "mock_real.html").resolve().as_uri()
    page = browser.new_page()
    page.goto(URL_ASLI)
    ring = pelajaran.jalankan_pelajaran(page, maks=10, timeout=4000)
    check("pelajaran: 5 halaman dikerjakan, berhenti di halaman terakhir, semua terverifikasi",
          ring == {"halaman": 5, "tak_terverifikasi": 0})
    check("pelajaran: See Answer tidak pernah diklik", page.evaluate("() => window.seeAnswerKlik") == 0)
    check("pelajaran: 5 tugas tercatat selesai",
          page.locator(".learning__tasksNav_task--done").count() == 5)
    check("pelajaran: modal Video Tutorials dari Help ditutup", page.locator("ngb-modal-window").count() == 0)
    check("pelajaran: Dictionary lalu Help sudah diklik (Help terbuka)", "settingsMenu__listCat--open" in
          page.locator("#settingsMenu__help").get_attribute("class"))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=drag")
    check("pelajaran: soal 'Drag ...' -> berhenti, tidak melompat ke Next",
          raises(lambda: pelajaran.jalankan_pelajaran(page, maks=10, timeout=4000),
                 pelajaran.JenisSoalTidakDikenal)
          and page.locator("#petunjuk").inner_text() == "Drag the correct answer."
          and page.locator(".learning__tasksNav_task--done").count() == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=kosong")
    check("pelajaran: select milik panel Dictionary tidak dianggap soal -> halaman tak dikenal",
          raises(lambda: pelajaran.jalankan_pelajaran(page, maks=10, timeout=4000),
                 pelajaran.JenisSoalTidakDikenal)
          and page.locator("#selectLanguage").input_value() == "")
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=tidakdikenal")
    check("pelajaran: jenis soal tak dikenal -> berhenti, tidak melompat",
          raises(lambda: pelajaran.jalankan_pelajaran(page, maks=10, timeout=4000),
                 pelajaran.JenisSoalTidakDikenal))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI)
    check("pelajaran: batas halaman ditaati", pelajaran.jalankan_pelajaran(
        page, maks=2, timeout=4000)["halaman"] == 2)
    page.close()
    browser.close()

    # --- Mode attach: "manusia" membuka + login, lalu bot menempel lewat CDP ---
    peramban = pw.chromium.launch(args=[f"--remote-debugging-port={PORT_CDP}"])
    # tab "error" dibuka lebih dulu (seperti 404 di ED); bot harus melewatinya
    decoy = peramban.new_page()
    decoy.goto(URLS["mock"] + "#/error.html")
    manusia = halaman_login(peramban, user, password)
    hasil = subprocess.run(
        [sys.executable, str(BASE / "bot.py"), "--target", "mock",
         "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        capture_output=True, text=True, timeout=120)
    check("mode attach: bot selesai (exit 0)", hasil.returncode == 0)
    check("mode attach: tugas terkerjakan di tab milik pengguna",
          manusia.locator("#header-status").inner_text() == "header 2 diklik"
          and manusia.locator("#completed").is_visible())
    check("mode attach: tidak membaca .env/password (tak ada langkah login)",
          "Isi username" not in hasil.stdout + hasil.stderr)
    ambil = subprocess.run(
        [sys.executable, str(BASE / "ambil_html.py"), "--target", "mock", "--nama", "uji_ambil",
         "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        capture_output=True, text=True, timeout=60)
    html0 = (LOG_DIR / "uji_ambil_frame0.html").read_text(encoding="utf-8")
    json0 = (LOG_DIR / "uji_ambil_elemen.json").read_text(encoding="utf-8")
    check("ambil_html: exit 0 + file hasil ada",
          ambil.returncode == 0 and (LOG_DIR / "uji_ambil.png").exists())
    check("ambil_html: elemen tugas terdaftar, script dibuang",
          "btn-start" in json0 and "header-btn-1" in json0 and "<script" not in html0)
    check("ambil_html: tidak mengubah halaman (hanya baca)",
          manusia.locator("#header-status").inner_text() == "header 2 diklik")
    check("ambil_html: --nama berbahaya ditolak", subprocess.run(
        [sys.executable, str(BASE / "ambil_html.py"), "--nama", "../x", "--attach", "http://x"],
        capture_output=True, text=True, timeout=30).returncode != 0)
    # --- Mode pantau: soal berganti -> hasil baru tersimpan otomatis ---
    for sisa in LOG_DIR.glob("uji_pantau*"):
        sisa.unlink()
    proses = subprocess.Popen(
        [sys.executable, str(BASE / "ambil_html.py"), "--target", "mock", "--nama", "uji_pantau",
         "--pantau", "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def tunggu_file(nama_file, detik=30):
        batas = time.monotonic() + detik
        while time.monotonic() < batas:
            if (LOG_DIR / nama_file).exists():
                return True
            manusia.wait_for_timeout(300)
        return False

    ada1 = tunggu_file("uji_pantau01_elemen.json")
    manusia.evaluate("() => { document.querySelector('#question-text').textContent"
                     " = 'Soal baru: where are you from?'; }")
    ada2 = tunggu_file("uji_pantau02_elemen.json")
    proses.send_signal(signal.SIGINT)
    try:
        proses.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proses.kill()
    check("pantau: soal pertama dan soal berganti tersimpan otomatis", ada1 and ada2)
    check("pantau: Ctrl+C berhenti rapi (exit 0)", proses.returncode == 0)
    kedua = LOG_DIR / "uji_pantau02_frame0.html"
    check("pantau: hasil kedua memuat teks soal baru",
          kedua.exists() and "Soal baru" in kedua.read_text(encoding="utf-8"))
    manusia.close()
    kosong = subprocess.run(
        [sys.executable, str(BASE / "bot.py"), "--target", "mock",
         "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        capture_output=True, text=True, timeout=60)
    check("mode attach: tab tidak ada -> bot berhenti (exit 1)", kosong.returncode == 1)
    check("mode attach: pesan error menyebut tab yang terlihat",
          "Tab yang terlihat bot" in kosong.stdout + kosong.stderr)
    peramban.close()

# --- Log dan screenshot ---
new_png = set(LOG_DIR.glob("*.png")) - before
check("screenshot kegagalan tersimpan di logs/", len(new_png) >= 1)
log_text = (LOG_DIR / "bot.log").read_text()
check("password tidak ada di logs/bot.log", password not in log_text)

# --- Target real tanpa selector ---
check("target real tanpa selector -> ditolak",
      raises(lambda: login(None, "real", URLS["real"], user, password), RuntimeError))

sys.exit(1 if failures else 0)

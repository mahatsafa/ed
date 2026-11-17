"""Uji otomatis di mock.html. Jalankan: python test_mock.py"""
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from bot import URLS, load_credentials
from helpers import LOG_DIR, setup_logger
from login import login
import diagnosa
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


def berurutan(page, maks=10):
    """Jalankan pengulang halaman; kembalikan (ringkasan, alasan berhenti)."""
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    return ring, pelajaran.kerjakan_berurutan(page, ring, maks, 4000)


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
    ring, alasan = berurutan(page)
    pelajaran.klik_header(page, 4000)
    check("pelajaran: 5 halaman dikerjakan, berhenti di halaman terakhir, semua terverifikasi",
          ring == {"halaman": 5, "tak_terverifikasi": 0} and alasan == "habis")
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
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.locator("#petunjuk").inner_text() == "Drag the correct answer."
          and page.locator(".learning__tasksNav_task--done").count() == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=dropdown")
    page.wait_for_selector(".DDLOptions__selected")
    check("dropdown kustom: dua dropdown terisi, daftar tertutup, tanpa Check/See Answer",
          pelajaran.isi_dropdown(page, 4000) is True
          and all(t.strip() for t in page.locator(".DDLOptions__selected").all_inner_texts())
          and page.locator(".DDLOptions__selected").count() == 2
          and page.locator(".DDLOptions__list").count() == 0
          and page.evaluate("() => window.seeAnswerKlik") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=kosong")
    check("pelajaran: select milik panel Dictionary tidak dianggap soal -> halaman tak dikenal",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.locator("#selectLanguage").input_value() == "")
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=tidakdikenal")
    check("pelajaran: jenis soal tak dikenal -> berhenti, tidak melompat",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI)
    ring, alasan = berurutan(page, maks=2)
    check("pelajaran: batas halaman ditaati", ring["halaman"] == 2 and alasan == "batas")
    page.close()

    # --- Auto-navigasi: dashboard -> unit -> lesson -> step, Test tidak disentuh ---
    URL_KURSUS = (BASE / "mock_kursus.html").resolve().as_uri()
    for nama, tambah in (("dari dashboard", ""), ("dari area belajar", "?mulai=area")):
        page = browser.new_page()
        page.goto(URL_KURSUS + tambah)
        ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
        status = page.evaluate("() => [[0,0],[0,1],[0,2],[1,0],[1,1],[1,2],[2,0]].map(([l,s]) => statusStep(l,s))")
        check(f"kursus {nama}: semua step non-Test selesai, Test tetap belum",
              status == ["done", "done", "notStarted", "done", "done", "notStarted", "done"])
        check(f"kursus {nama}: 7 tugas selesai, Test tak diklik, See Answer nol, 0 tak terverifikasi",
              page.evaluate("() => selesaiJumlah()") == 7 and page.evaluate("() => testDikerjakan") == 0
              and page.evaluate("() => seeAnswerKlik") == 0 and ring["tak_terverifikasi"] == 0)
        check(f"kursus {nama}: berakhir di dashboard, Dictionary lalu Help sudah diklik",
              page.locator("#home").is_visible()
              and "settingsMenu__listCat--open" in page.locator("#settingsMenu__help").get_attribute("class"))
        page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=semua")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: semua unit Completed! -> berhenti tanpa mengerjakan apa pun",
          ring["halaman"] == 0 and page.evaluate("() => selesaiJumlah()") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=statuskosong")
    check("kursus: status progres tak terbaca -> berhenti (gagal tertutup)",
          raises(lambda: pelajaran.jalankan_pelajaran(page, timeout=4000), pelajaran.JenisSoalTidakDikenal)
          and page.evaluate("() => selesaiJumlah()") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=tanpajudul&mulai=area")
    page.wait_for_selector("#learning__dropDownListTitleW_lessons .learning__dropDownListTitle[title]")
    check("kursus: judul step tak terbaca -> anggap Test (gagal tertutup), tidak ada yang dikerjakan",
          pelajaran.sedang_test(page) is True
          and berurutan(page)[1] == "test" and page.evaluate("() => selesaiJumlah()") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI)
    check("kursus: halaman bukan dashboard/area belajar -> ditolak",
          raises(lambda: pelajaran.jalankan_pelajaran(page, timeout=2000), pelajaran.JenisSoalTidakDikenal))
    page.close()

    # --- Diagnosa (baca saja) di halaman tiruan ---
    page = browser.new_page()
    page.goto(URL_ASLI)
    folder_diag = LOG_DIR / "uji_diagnosa"
    hasil_diag = diagnosa.rekam_state(page, folder_diag, setup_logger())
    utama = hasil_diag[0]
    ring_json = json.loads((folder_diag / "ringkasan.json").read_text(encoding="utf-8"))
    check("diagnosa: ringkasan.json + html + screenshot frame utama ada",
          ring_json["frame"][0]["frame"] == 0 and (folder_diag / "frame0.html").exists()
          and (folder_diag / "frame0.png").exists())
    check("diagnosa: #CheckAnswer dan a.tasksBtnext terhitung",
          utama["selektor"]["#CheckAnswer"] >= 1 and utama["selektor"]["a.tasksBtnext"] >= 1)
    check("diagnosa: tombol Next terdeteksi", any(t["teks"] == "Next" for t in utama["tombol_nav"]))
    check("diagnosa: tidak mengklik apa pun (tak ada tugas selesai, See Answer nol)",
          page.locator(".learning__tasksNav_task--done").count() == 0
          and page.evaluate("() => window.seeAnswerKlik") == 0)
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
    diag = subprocess.run(
        [sys.executable, str(BASE / "diagnosa.py"), "--target", "mock", "--state", "satu",
         "--state", "dua", "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        input="\n\n", capture_output=True, text=True, timeout=60)
    akar_diag = sorted(LOG_DIR.glob("diagnosa_*"))[-1] if list(LOG_DIR.glob("diagnosa_*")) else None
    check("diagnosa CLI: exit 0 dan dua state tersimpan",
          diag.returncode == 0 and akar_diag is not None
          and (akar_diag / "satu" / "ringkasan.json").exists()
          and (akar_diag / "dua" / "ringkasan.json").exists())
    check("diagnosa CLI: nama state berbahaya ditolak", subprocess.run(
        [sys.executable, str(BASE / "diagnosa.py"), "--state", "../x", "--attach", "http://x"],
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
    # --- Diagnosa --pantau: perubahan kelas CSS (tanpa ubah teks) harus ikut terekam ---
    lama_d = set(LOG_DIR.glob("diagnosa_*"))  # rekaman lama (mis. dari situs asli) tidak dihitung

    def pantau_baru(n):
        return [d / f"pantau_{n:03d}" / "ringkasan.json" for d in set(LOG_DIR.glob("diagnosa_*")) - lama_d
                if (d / f"pantau_{n:03d}" / "ringkasan.json").exists()]
    proses_d = subprocess.Popen(
        [sys.executable, str(BASE / "diagnosa.py"), "--target", "mock", "--pantau",
         "--attach", f"http://127.0.0.1:{PORT_CDP}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    batas_d = time.monotonic() + 40
    while time.monotonic() < batas_d and not pantau_baru(1):
        manusia.wait_for_timeout(300)
    manusia.evaluate("() => document.querySelector('#question-text').classList.add('tandaBaru')")
    while time.monotonic() < batas_d and not pantau_baru(2):
        manusia.wait_for_timeout(300)
    proses_d.send_signal(signal.SIGINT)
    try:
        proses_d.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proses_d.kill()
    check("diagnosa pantau: tampilan awal dan perubahan kelas CSS terekam otomatis",
          bool(pantau_baru(1)) and bool(pantau_baru(2)))
    check("diagnosa pantau: Ctrl+C berhenti rapi (exit 0)", proses_d.returncode == 0)
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

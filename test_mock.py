"""Uji otomatis di mock.html. Jalankan: python test_mock.py"""
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from bot import URLS, buka_chrome, cdp_siap, load_credentials
from helpers import LOG_DIR, setup_logger
from login import login
import belajar
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
    check("pelajaran: 6 halaman dikerjakan, berhenti di halaman terakhir, semua terverifikasi",
          ring == {"halaman": 6, "tak_terverifikasi": 0} and alasan == "habis")
    check("pelajaran: See Answer tidak pernah diklik", page.evaluate("() => window.seeAnswerKlik") == 0)
    check("pelajaran: 6 tugas tercatat selesai",
          page.locator(".learning__tasksNav_task--done").count() == 6)
    check("pelajaran: modal Video Tutorials dari Help ditutup", page.locator("ngb-modal-window").count() == 0)
    check("pelajaran: Dictionary lalu Help sudah diklik (Help terbuka)", "settingsMenu__listCat--open" in
          page.locator("#settingsMenu__help").get_attribute("class"))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=drag")
    ring, alasan = berurutan(page)
    check("pelajaran: soal 'Drag ...' (cloze) dikerjakan: 3 kotak terisi, terverifikasi, See Answer nol",
          ring == {"halaman": 1, "tak_terverifikasi": 0} and alasan == "habis"
          and page.locator(".prCLZ__regContainer .dnditem").count() == 3
          and page.locator(".learning__tasksNav_task--done").count() == 1
          and page.evaluate("() => window.seeAnswerKlik") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=cocok")
    ring, alasan = berurutan(page)
    check("pelajaran: pencocokan dikerjakan: 3 baris terisi, terverifikasi, See Answer nol",
          ring == {"halaman": 1, "tak_terverifikasi": 0} and alasan == "habis"
          and page.locator(".prMT_T2T__regContainer .dnditem").count() == 3
          and page.locator(".learning__tasksNav_task--done").count() == 1
          and page.evaluate("() => window.seeAnswerKlik") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=mikrofon")
    check("pelajaran: soal suara (webRtc) -> berhenti, 0 opsi diklik, tidak selesai",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.evaluate("() => window.opsiKlik") == 0
          and page.locator(".learning__tasksNav_task--done").count() == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=teksbebas")
    check("pelajaran: isian teks (textarea, instruksi tanpa 'Type') -> berhenti, tidak melompat",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.locator("#ta").input_value() == ""
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
    page.goto(URL_ASLI + "?skenario=pilihan")
    page.wait_for_selector(".prMCQ__qaSet")
    check("pilihan: tiap pertanyaan (2) tepat satu terpilih, opsi pertama, See Answer nol",
          pelajaran.pilih_radio(page, 4000) is True
          and page.locator(".prMCQ__qaSet").count() == 2
          and page.evaluate("() => [...document.querySelectorAll('.prMCQ__qaSet')]"
                            ".map(s => [...s.querySelectorAll('input:checked')].map(i => i.id))")
          == [["question-1_answer-1"], ["question-2_answer-4"]]
          and page.evaluate("() => window.seeAnswerKlik") == 0)
    page.close()

    def opsi(n, tersembunyi=False):
        return (f'<div class="prMCQ__answers{" hide" if tersembunyi else ""}"><input type="radio" class="layout__radio" '
                f'id="question-1_answer-{n}"><label for="question-1_answer-{n}">opsi {n}</label></div>')
    page = browser.new_page()  # situs asli: opsi "None" tersembunyi (.hide) berada di urutan DOM pertama
    page.set_content('<style>.hide { display: none; }</style><div class="prMCQ__qaSet">'
                     + opsi(5, True) + opsi(4) + opsi(1) + '</div>')
    check("pilihan: opsi tersembunyi di urutan pertama dilewati; opsi terlihat pertama (answer-4) yang dipilih",
          pelajaran.pilih_radio(page, 3000) is True
          and page.evaluate("() => [...document.querySelectorAll('input:checked')].map(i => i.id)") == ["question-1_answer-4"])
    page.close()
    page = browser.new_page()
    page.set_content('<style>.hide { display: none; }</style><div class="prMCQ__qaSet">' + opsi(5, True) + '</div>')
    check("pilihan: tak ada opsi terlihat -> berhenti, tidak ada yang diklik",
          raises(lambda: pelajaran.pilih_radio(page, 2000), pelajaran.JenisSoalTidakDikenal)
          and page.locator("input:checked").count() == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=radioluar")
    page.wait_for_selector("input.layout__radio")
    check("pilihan: radio di luar .prMCQ__qaSet -> berhenti, tidak ada yang diklik",
          raises(lambda: pelajaran.pilih_radio(page, 2000), pelajaran.JenisSoalTidakDikenal)
          and page.locator("input:checked").count() == 0)
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
    page.goto(URL_KURSUS + "?skenario=geser")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: daftar tertutup bergeser keluar layar -> dibuka lagi, 7 tugas selesai, Test tak diklik",
          page.evaluate("() => selesaiJumlah()") == 7 and page.evaluate("() => testDikerjakan") == 0
          and page.evaluate("() => seeAnswerKlik") == 0 and ring["tak_terverifikasi"] == 0)
    page.close()

    for nama, tambah in (("dari dashboard", "?skenario=kunci"), ("mulai di intro Test", "?skenario=kunci&mulai=test")):
        page = browser.new_page()
        page.goto(URL_KURSUS + tambah)
        ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
        check(f"kursus daftar lesson terkunci di Test ({nama}): 7 tugas selesai, Test tak diklik, See Answer nol",
              page.evaluate("() => selesaiJumlah()") == 7 and page.evaluate("() => testDikerjakan") == 0
              and page.evaluate("() => seeAnswerKlik") == 0 and ring["tak_terverifikasi"] == 0)
        page.close()

    for nama, tambah in (("biasa", ""), ("daftar lesson terkunci, mulai di intro Test", "?skenario=kunci&mulai=test")):
        page = browser.new_page()
        page.goto(URL_KURSUS + tambah)
        ring = pelajaran.jalankan_pelajaran(page, timeout=4000, hanya_baca=True)
        rencana = ring["rencana"]
        akan = [x for r in rencana for x in r["dikerjakan"]]
        lewat = [x for r in rencana for x in r["dilewati"]]
        check(f"kursus uji kering ({nama}): 5 step direncanakan, 2 Test dilewati, tak ada yang dijawab",
              len(akan) == 5 and not any("Test" in x for x in akan) and len(lewat) == 2
              and ring["halaman"] == 0 and page.evaluate("() => selesaiJumlah()") == 0
              and page.evaluate("() => testDikerjakan") == 0 and page.evaluate("() => seeAnswerKlik") == 0)
        page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=hanyatest&mulai=test")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: lesson hanya berisi Test dan daftar terkunci -> unit dilewati, kembali ke dashboard, 0 tugas",
          ring["halaman"] == 0 and page.evaluate("() => selesaiJumlah()") == 0
          and page.evaluate("() => testDikerjakan") == 0 and page.locator("#home").is_visible())
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=balik")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: kartu unit berbalik ke daftar lesson -> lesson tak terkunci diklik, 7 tugas selesai, Test tak diklik",
          page.evaluate("() => selesaiJumlah()") == 7 and page.evaluate("() => testDikerjakan") == 0
          and page.evaluate("() => lessonKunciKlik") == 0 and ring["tak_terverifikasi"] == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=balikkunci")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: kartu berbalik, semua lesson terkunci -> unit dilewati, 0 tugas, lesson terkunci tak diklik",
          ring["halaman"] == 0 and page.evaluate("() => selesaiJumlah()") == 0
          and page.evaluate("() => lessonKunciKlik") == 0 and page.locator("#home").is_visible())
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
    check("kursus: pembacaan daftar gagal -> HTML daftar tersimpan di logs/",
          any(f.stat().st_size > 0 for f in LOG_DIR.glob("*_daftar_*.html")))
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?mulai=area")
    page.wait_for_selector("#learning__dropDownListW_steps .learning__dropDownList_item", state="attached")
    page.click("#learning__dropDownListTitleW_steps")
    terhalang = raises(lambda: page.click("#learning__dropDownListTitleW_steps", timeout=500), Exception)
    pelajaran.tutup_daftar(page, "steps", timeout=4000)
    check("kursus: overlay menghalangi judul daftar yang terbuka; tutup_daftar menutupnya lewat overlay",
          terhalang and not pelajaran.daftar_terbuka(page, "steps")
          and not page.locator(".utils__siteOverlay--LABody").is_visible()
          and page.evaluate("() => overlayBawahKlik") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=teststatuskosong")
    ring = pelajaran.jalankan_pelajaran(page, timeout=4000)
    check("kursus: step Test tanpa penanda status -> tetap jalan, 7 tugas selesai, Test tak diklik",
          page.evaluate("() => selesaiJumlah()") == 7 and page.evaluate("() => testDikerjakan") == 0
          and page.evaluate("() => seeAnswerKlik") == 0 and ring["tak_terverifikasi"] == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS + "?skenario=tanpajudul&mulai=area")
    page.wait_for_selector("#learning__dropDownListTitleW_lessons .learning__dropDownListTitle[title]")
    check("kursus: judul step tak terbaca -> anggap Test (gagal tertutup), tidak ada yang dikerjakan",
          pelajaran.sedang_test(page) is True
          and berurutan(page)[1] == "test" and page.evaluate("() => selesaiJumlah()") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_KURSUS)
    pelajaran.buka_unit(page, set(), 4000)
    awal = pelajaran.cari_target(page, set(), 4000)
    lain = pelajaran.cari_target(page, set(), 4000, {(awal[0], awal[2])})
    check("kursus: step yang dilewati (lewat_step) tidak dipilih lagi, step berikutnya dipilih",
          awal is not None and lain is not None and (lain[0], lain[2]) != (awal[0], awal[2]))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI)
    check("kursus: halaman bukan dashboard/area belajar -> ditolak",
          raises(lambda: pelajaran.jalankan_pelajaran(page, timeout=2000), pelajaran.JenisSoalTidakDikenal))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI)
    rumah_asli, rumah_timeout = pelajaran.click, []
    pelajaran.click = lambda pg, loc, nama, timeout=0, **o: rumah_timeout.append((nama, timeout))
    try:
        pelajaran.kembali_ke_dashboard(page, 4000)
    except Exception:
        pass  # wait_visible dashboard boleh gagal; yang diperiksa hanya batas klik
    finally:
        pelajaran.click = rumah_asli
    check("kursus: klik ikon rumah memakai batas tunggu dashboard (navigasi lambat), bukan batas klik biasa",
          rumah_timeout == [("ikon_rumah", pelajaran.TUNGGU_DASHBOARD_MS)])
    page.close()

    page = browser.new_page()
    kamus = '<div id="DictionaryPanelContainer" style="display:none"><input type="text"></div>'
    bacaan = '<article><p>Teks artikel.</p></article>' + kamus
    nav = '<a class="tasksBtnext" href="#">Next</a>'
    def bacaan_ok(html):
        page.set_content(html)
        return pelajaran.halaman_bacaan(page)
    check("bacaan: artikel + Next + kamus tersembunyi -> halaman bacaan", bacaan_ok(bacaan + nav) is True)
    check("bacaan: tanpa Next -> bukan bacaan", bacaan_ok(bacaan) is False)
    check("bacaan: ada Check Answer terlihat -> bukan bacaan",
          bacaan_ok(bacaan + nav + '<li id="CheckAnswer">Check</li>') is False)
    check("bacaan: ada isian teks terlihat -> bukan bacaan", bacaan_ok(bacaan + nav + '<input type="text">') is False)
    check("bacaan: ada tombol/seret terlihat -> bukan bacaan",
          bacaan_ok(bacaan + nav + '<button>Ok</button>') is False
          and bacaan_ok(bacaan + nav + '<div class="dnditem">kata</div>') is False)
    page.set_content(bacaan + nav)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("bacaan: kerjakan_halaman tidak berhenti dan tidak mengklik apa pun",
          not raises(lambda: pelajaran.kerjakan_halaman(page, ring, 2000), pelajaran.JenisSoalTidakDikenal))
    page.set_content(bacaan + nav + '<input type="text">')
    check("bacaan: halaman berisian teks tetap berhenti (gagal tertutup)",
          raises(lambda: pelajaran.kerjakan_halaman(page, ring, 2000), pelajaran.JenisSoalTidakDikenal))
    page.close()

    page = browser.new_page()
    isi_a = ('<p id="t">halaman A</p><input type="text"><a class="tasksBtnext" href="#" onclick="'
             "document.getElementById('t').textContent='halaman B';document.querySelector('input').remove();"
             'return false">Next</a>')
    page.set_content(isi_a)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("bantuan: tanpa tanya, halaman tak dikenal -> bot berhenti (gagal tertutup)",
          raises(lambda: pelajaran.kerjakan_berurutan(page, ring, 5, 2000), pelajaran.JenisSoalTidakDikenal))
    page.set_content(isi_a)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    ditanya = []
    alasan_henti = pelajaran.kerjakan_berurutan(page, ring, 5, 2000, tanya=lambda pg, alasan: ditanya.append(alasan))
    check("bantuan: dengan tanya, bot bertanya sekali lalu lanjut Next ke halaman berikut",
          len(ditanya) == 1 and "halaman B" in page.inner_text("body") and ring["manual"] == 1
          and alasan_henti == "habis")
    page.close()

    page = browser.new_page()
    page.set_content('<button id="btn-a" class="x">Mulai</button><input id="isi" type="text">'
                     '<input id="rahasia" type="password">')
    def pengguna():  # meniru pengguna: klik, ketik
        page.click("#btn-a")
        page.fill("#isi", "halo")
        page.fill("#rahasia", "sandi123")
    awalan = belajar.rekam_dan_tunggu(page, "uji", pengguna)
    rek = json.loads((LOG_DIR / f"{awalan}_aksi.json").read_text(encoding="utf-8"))
    jenis = [a["jenis"] for a in rek["aksi"]]
    check("belajar: klik dan isian pengguna terekam (selektor + nilai)",
          "click" in jenis and any("button#btn-a" in a["jalur"] for a in rek["aksi"] if a["jenis"] == "click")
          and any(a["nilai"] == "halo" for a in rek["aksi"]))
    check("belajar: isian password tidak disimpan nilainya",
          all(a["nilai"] is None for a in rek["aksi"] if "rahasia" in a["jalur"])
          and "sandi123" not in json.dumps(rek))
    check("belajar: HTML sebelum dan sesudah tersimpan",
          (LOG_DIR / f"{awalan}_sebelum_frame0.html").exists() and (LOG_DIR / f"{awalan}_sesudah_frame0.html").exists())
    belajar.MAX_AKSI = 3
    page.set_content('<button id="btn-a">Mulai</button>')  # dokumen baru: perekam bersih
    awalan = belajar.rekam_dan_tunggu(page, "batas", lambda: [page.click("#btn-a") for _ in range(5)])
    belajar.MAX_AKSI = 300
    check("belajar: jumlah aksi dibatasi",
          len(json.loads((LOG_DIR / f"{awalan}_aksi.json").read_text(encoding="utf-8"))["aksi"]) == 3)
    page.close()

    page = browser.new_page()
    kotak_dikte = "".join(f'<div class="prOpenEnded__qaSet"><textarea class="prOpenEnded__qaItemText prOpenEnded__qaItemText--textarea"></textarea></div>' for _ in range(3))
    dikte = ('<div class="learning__headerIW">Type the sentences that you hear in the dictation.</div>' + kotak_dikte
             + '<ul><li id="CheckAnswer">Check</li></ul><a class="tasksBtnext" href="#">Next</a>')
    page.set_content(dikte)
    check("dikte: tiga textarea terisi, handler melapor dikerjakan",
          pelajaran.isi_teks_bebas(page, 2000) is True
          and page.eval_on_selector_all(".prOpenEnded__qaItemText--textarea", "els => els.every(e => e.value === 'a')"))
    page.set_content(dikte)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    pelajaran.kerjakan_halaman(page, ring, 2000)
    check("dikte: instruksi 'Type ...' tidak lagi membuat bot berhenti; terisi dan Check Answer diklik",
          page.eval_on_selector_all(".prOpenEnded__qaItemText--textarea", "els => els.every(e => e.value === 'a')"))
    page.set_content('<div class="learning__headerIW">Type the answer.</div><textarea></textarea>'
                     '<ul><li id="CheckAnswer">Check</li></ul><a class="tasksBtnext" href="#">Next</a>')
    check("dikte: textarea lain (bukan prOpenEnded) tetap membuat bot berhenti",
          raises(lambda: pelajaran.kerjakan_halaman(page, ring, 2000), pelajaran.JenisSoalTidakDikenal))
    page.set_content("".join('<textarea class="prOpenEnded__qaItemText--textarea"></textarea>' for _ in range(pelajaran.MAX_TEKS_BEBAS + 1)))
    check("dikte: terlalu banyak textarea -> berhenti (batas atas)",
          raises(lambda: pelajaran.isi_teks_bebas(page, 2000), pelajaran.JenisSoalTidakDikenal))
    page.close()

    # --- Reminder dan video terlambat (potongan HTML) ---
    def app_reminder(halaman2):
        return ('<div class="learning__tasksNav_tasksW">' + "".join(
            f'<div class="learning__tasksNav_task{" learning__tasksNav_task--current" if i == 3 else ""}">{i}</div>'
            for i in (1, 2, 3)) + '</div><div id="isi">halaman 3</div>' + halaman2 +
            '<a class="tasksBtnext" href="#">Next</a>'
            '<div id="rem" style="display:none"><p>You need to complete the activity 2 to achieve progress in this step.</p>'
            '<a id="c" href="#">Continue</a> <a id="s" href="#">Stay in this step</a></div>'
            '<script>let aktif = 3, selesai2 = false, kata = "";'
            'const item = [...document.querySelectorAll(".learning__tasksNav_task")];'
            'const pilih = (n) => { aktif = n; item.forEach((e, i) => e.classList.toggle("learning__tasksNav_task--current", i + 1 === n));'
            ' document.getElementById("isi").textContent = "halaman " + n + kata; if (n === 2) selesai2 = !document.querySelector("input[type=text]"); };'
            'item.forEach((e, i) => e.addEventListener("click", () => pilih(i + 1)));'
            'document.querySelector(".tasksBtnext").addEventListener("click", (ev) => { ev.preventDefault();'
            ' if (aktif === 3 && !selesai2) document.getElementById("rem").style.display = "block";'
            ' else if (aktif === 3) { kata = " selesai"; pilih(3); } });'
            'document.getElementById("s").addEventListener("click", (ev) => { ev.preventDefault(); document.getElementById("rem").style.display = "none"; });'
            'document.getElementById("c").addEventListener("click", (ev) => { ev.preventDefault(); document.getElementById("rem").style.display = "none"; window.lewat = true; });'
            '</script>')
    page = browser.new_page()
    page.set_content(app_reminder("<p>artikel</p>"))
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    page.click(".tasksBtnext")
    check("reminder: jendela terdeteksi", pelajaran.reminder_terlihat(page) is True)
    check("reminder: tetap di step, kerjakan halaman 2, balik, Next lagi -> lanjut",
          pelajaran.selesaikan_reminder(page, ring, 3000) == "lanjut" and "selesai" in page.inner_text("#isi")
          and not pelajaran.reminder_terlihat(page))
    page.close()
    page = browser.new_page()  # halaman baru: skrip tiruan memakai let global
    page.set_content(app_reminder('<input type="text">'))  # halaman 2 punya isian teks: tak bisa dikerjakan bot
    page.click(".tasksBtnext")
    check("reminder: halaman tak bisa dikerjakan -> Continue (step dilewati)",
          pelajaran.selesaikan_reminder(page, ring, 3000) == "lewat" and page.evaluate("() => window.lewat === true"))
    page.close()
    page = browser.new_page()
    page.set_content('<video id="MP" width="100" height="60"></video>'
                     '<script>window.klik = "";'
                     'document.getElementById("MP").addEventListener("click", () => { window.klik += "video"; });'
                     'setTimeout(() => { const o = document.createElement("div"); o.className = "learning__RAMRButton learning__RAMRButton--play";'
                     'o.style.cssText = "position:absolute;left:0;top:0;width:100px;height:60px;";'
                     'o.addEventListener("click", () => { window.klik += "tombol"; }); document.body.appendChild(o); }, 700);</script>')
    raises(lambda: pelajaran.putar_video(page, 4000), Exception)  # tak ada media sungguhan: pemeriksaan "terputar" gagal
    check("video: tombol putar yang muncul terlambat dipakai, bukan elemen video",
          page.evaluate("() => window.klik") == "tombol")
    page.close()

    # --- Video harus diputar sampai habis; Reminder media di iframe (potongan HTML, properti media dipalsukan) ---
    def media_palsu(durasi_js, main_js="false"):
        return ('<script>window.main = ' + main_js + '; window.t = 1; window.selesai = false; window.dur = ' + durasi_js + ';'
                'const P = HTMLMediaElement.prototype;'
                'Object.defineProperty(P, "paused", {get: () => !window.main});'
                'Object.defineProperty(P, "currentTime", {get: () => window.t});'
                'Object.defineProperty(P, "duration", {get: () => window.dur});'
                'Object.defineProperty(P, "ended", {get: () => window.selesai});</script>')
    mulai_palsu = ('<script>document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => {'
                   ' if (window.main) return; window.main = true; window.t = 0.5;'
                   ' setTimeout(() => { window.t = 2; window.selesai = true; }, 1200); });</script>')
    video_palsu = ('<video width="200" height="100"></video>'
                   '<div class="learning__RAMRButton learning__RAMRButton--play" style="width:50px;height:30px">p</div>')
    page = browser.new_page()
    page.set_content(media_palsu("2") + video_palsu + mulai_palsu)
    check("video: putar_video menunggu media selesai (ended), bukan hanya mulai",
          pelajaran.putar_video(page, 4000) is True and page.evaluate("() => window.selesai") is True)
    page.close()
    page = browser.new_page()
    page.set_content(media_palsu("NaN", "true") + '<video width="200" height="100"></video>')
    check("video: durasi tak terbaca (NaN) -> berhenti, tidak menunggu tanpa batas",
          raises(lambda: pelajaran.putar_video(page, 2000), pelajaran.JenisSoalTidakDikenal))
    page.close()
    page = browser.new_page()
    page.set_content(media_palsu(str(pelajaran.MAX_DURASI_MEDIA + 1), "true") + '<video width="200" height="100"></video>')
    check("video: durasi di atas batas atas -> berhenti",
          raises(lambda: pelajaran.putar_video(page, 2000), pelajaran.JenisSoalTidakDikenal))
    page.close()
    page = browser.new_page()
    page.set_content(  # Reminder di iframe: teks body tak berubah saat muncul, seperti di situs asli
        '<div id="isi">awal</div><a class="tasksBtnext" href="#">Next</a>' + media_palsu("2") + video_palsu +
        '<iframe id="f" style="display:none" srcdoc=\'<h3>Reminder!</h3>'
        '<p>You need to play the video/audio to achieve progress in this step.</p>'
        '<a href="#" onclick="parent.fc()">Continue</a> <a href="#" onclick="parent.fs()">Stay in this step</a>\'></iframe>'
        '<script>let ack = false; const f = document.getElementById("f");'
        'window.fs = () => { ack = true; f.style.display = "none"; };'
        'window.fc = () => { window.lewat = true; f.style.display = "none"; };'
        'document.querySelector(".tasksBtnext").addEventListener("click", (ev) => { ev.preventDefault();'
        ' if (!ack) f.style.display = "block"; else document.getElementById("isi").textContent = "akhir"; });</script>'
        + mulai_palsu)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    alasan = pelajaran.kerjakan_berurutan(page, ring, 2, 4000)
    check("reminder media (iframe): Next tanpa perubahan teks tak dianggap 'habis'; tetap, putar, Next -> halaman berganti",
          page.inner_text("#isi") == "akhir" and ring["halaman"] == 2 and alasan == "habis"
          and page.evaluate("() => window.lewat") is None)
    page.close()
    page = browser.new_page()
    page.set_content('<h3>Reminder!</h3><p>You need to do something else.</p><a href="#">Continue</a>')
    check("reminder: teks tak dikenal -> berhenti, Continue tidak diklik",
          pelajaran.reminder_terlihat(page) is True
          and raises(lambda: pelajaran.selesaikan_reminder(page, ring, 2000), pelajaran.JenisSoalTidakDikenal))
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

    # --- Mode buka: bot membuka Chromium sendiri dengan port debug (tanpa jendela untuk uji) ---
    port_buka = 9444
    profil_uji = LOG_DIR / "profil_uji_buka"
    proses_buka = buka_chrome(pw, URLS["mock"], port_buka, tanpa_jendela=True, profil=profil_uji)
    try:
        sambung = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port_buka}")
        urls_buka = [pg.url for c in sambung.contexts for pg in c.pages]
        check("buka: Chromium terbuka di port debug dan memuat URL target",
              proses_buka is not None and cdp_siap(port_buka) and any("mock.html" in u for u in urls_buka))
        check("buka: port sudah dipakai -> dipakai ulang, tidak membuka dobel",
              buka_chrome(pw, URLS["mock"], port_buka, tanpa_jendela=True, profil=profil_uji) is None)
        sambung.close()
    finally:
        if proses_buka is not None:
            proses_buka.terminate()
            proses_buka.wait(timeout=20)
    check("buka: setelah ditutup, port debug mati", not cdp_siap(port_buka))

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
    check("--hanya-baca untuk target mock -> ditolak",
          subprocess.run([sys.executable, str(BASE / "bot.py"), "--target", "mock", "--hanya-baca"],
                         capture_output=True, text=True, timeout=30).returncode != 0)
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

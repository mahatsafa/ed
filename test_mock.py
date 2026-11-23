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
    page.goto(URL_ASLI + "?skenario=klasifikasi")
    ring, alasan = berurutan(page)
    check("pelajaran: klasifikasi (prCl): 5 item dibagi ke 2 kolom (3+2), bank kosong, terverifikasi, See Answer nol",
          ring == {"halaman": 1, "tak_terverifikasi": 0} and alasan == "habis"
          and page.locator(".prCl__container--bank .dnditem").count() == 0
          and page.evaluate("() => [...document.querySelectorAll('.prCl__container--normal .dndZone')]"
                            ".map(z => z.querySelectorAll('.dnditem').length)") == [3, 2]
          and page.locator(".learning__tasksNav_task--done").count() == 1
          and page.evaluate("() => window.seeAnswerKlik") == 0)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=gambar")
    ring, alasan = berurutan(page)
    check("pelajaran: kata ke gambar (prTextToPic): 3 gambar masing-masing satu kata, terverifikasi",
          ring == {"halaman": 1, "tak_terverifikasi": 0} and alasan == "habis"
          and page.evaluate("() => [...document.querySelectorAll('.prTextToPic__container--reg .dndZone')]"
                            ".map(z => z.querySelectorAll('.dnditem').length)") == [1, 1, 1]
          and page.locator(".learning__tasksNav_task--done").count() == 1)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=dndasing")
    check("pelajaran: zona seret tanpa handler -> berhenti (tidak diam-diam dilewati), tak ada item bergeser",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.locator("#x_0 .dnditem").count() == 0 and page.locator(".learning__tasksNav_task--done").count() == 0)
    page.close()

    page = browser.new_page()  # kartu Reminder di iframe memuat belakangan: selesaikan_reminder tidak boleh menyimpulkan "hilang"
    page.set_content(
        '<div id="isi">awal</div><a class="tasksBtnext" href="#">Next</a>'
        '<div id="EdoFrameBox" style="position:fixed;inset:0;background:#0006;z-index:9"></div>'
        '<script>setTimeout(() => { document.getElementById("EdoFrameBox").innerHTML = "<div>Reminder! You need to complete the '
        'activities 9 and 8 to achieve progress in this step. <a id=\\"c\\" href=\\"#\\">Continue</a></div>"; '
        'document.getElementById("c").addEventListener("click", (e) => { e.preventDefault(); window.lewat = true; '
        'document.getElementById("EdoFrameBox").remove(); }); }, 800);</script>')
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("reminder: kartu terlambat dimuat -> ditunggu; nomor di luar pager -> Continue (lewat), bukan 'lanjut' dini",
          pelajaran.selesaikan_reminder(page, ring, 3000) == "lewat" and page.evaluate("() => window.lewat === true"))
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=mikrofon")
    ring, alasan = berurutan(page)
    check("pelajaran: soal suara (webRtc): Start diklik sekali, direkam sampai 'Try again', 0 opsi diklik, tercatat selesai",
          ring == {"halaman": 1, "tak_terverifikasi": 0} and alasan == "habis"
          and page.evaluate("() => window.rekam") == 1 and page.evaluate("() => window.opsiKlik") == 0
          and page.locator(".continue.retry").count() == 1
          and page.locator(".learning__tasksNav_task--done").count() == 1)
    page.close()

    page = browser.new_page()
    page.goto(URL_ASLI + "?skenario=mikrofonmacet")
    asli_sesi = pelajaran.TUNGGU_SESI_MS
    pelajaran.TUNGGU_SESI_MS = 1000
    check("pelajaran: sesi suara tak terbentuk (Start tetap nonaktif) -> berhenti, tidak direkam, 0 opsi diklik",
          raises(lambda: berurutan(page), pelajaran.JenisSoalTidakDikenal)
          and page.evaluate("() => window.rekam") == 0 and page.evaluate("() => window.opsiKlik") == 0
          and page.locator(".learning__tasksNav_task--done").count() == 0)
    pelajaran.TUNGGU_SESI_MS = asli_sesi
    page.close()

    page = browser.new_page()  # halaman yang sudah direkam ('Try again' tampil): tidak direkam ulang
    page.set_content('<div class="answersWrapper mcq webRtc"><div class="speakingInteractButtonWrapper">'
                     '<div class="buttonWrapper continueWrapper"><a class="button continue retry">Try again</a></div></div></div>'
                     '<script>window.klik = 0; document.querySelector(".continue").addEventListener("click", () => { window.klik++; });</script>')
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("suara: sudah 'Try again' -> dianggap direkam, tombol tidak diklik",
          pelajaran.rekam_suara(page, ring, 3000) is True and page.evaluate("() => window.klik") == 0)
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
    check("bacaan: tombol menu header (sitemenu__) tidak dihitung kontrol soal (situs asli Lesson 2) -> bacaan",
          bacaan_ok(bacaan + nav + '<button id="sitemenu__openMenuBtn">menu</button>') is True)
    check("bacaan: halaman dialog peran (Interact, a.button Start) -> BUKAN bacaan (situs asli Lesson 3 Interact 1)",
          bacaan_ok(bacaan + nav + '<div class="speakingInteract"><a class="button continue">Start</a></div>') is False)
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
    def app_reminder(halaman2, teks="activity 2"):
        return ('<div class="learning__tasksNav_tasksW">' + "".join(
            f'<div class="learning__tasksNav_task{" learning__tasksNav_task--current" if i == 3 else ""}">{i}</div>'
            for i in (1, 2, 3)) + '</div><div id="isi">halaman 3</div>' + halaman2 +
            '<a class="tasksBtnext" href="#">Next</a>'
            '<div id="rem" style="display:none"><p>You need to complete the ' + teks + ' to achieve progress in this step.</p>'
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
    page = browser.new_page()  # situs asli: "activities 3, 4 and 7" (jamak, beberapa nomor)
    page.set_content(app_reminder("<p>artikel</p>", "activities 2 and 3"))
    page.click(".tasksBtnext")
    check("reminder jamak ('activities 2 and 3'): nomor pertama yang bisa dikerjakan dipakai -> lanjut",
          pelajaran.reminder_terlihat(page) is True
          and pelajaran.selesaikan_reminder(page, ring, 3000) == "lanjut" and "selesai" in page.inner_text("#isi"))
    page.close()
    page = browser.new_page()  # Reminder sudah terbuka sebelum bot mengerjakan halaman apa pun (situs asli, 11:15)
    page.set_content(app_reminder("<p>artikel</p>"))
    page.evaluate("() => { document.getElementById('rem').style.display = 'block'; }")
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    alasan = pelajaran.kerjakan_berurutan(page, ring, 1, 3000)
    check("reminder sudah terbuka sejak awal: ditangani sebelum halaman dikerjakan",
          not pelajaran.reminder_terlihat(page) and "selesai" in page.inner_text("#isi") and alasan in ("batas", "habis"))
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

    page = browser.new_page()  # situs asli, halaman menulis: tombol putar tersisa di luar layar, tanpa video
    page.set_content('<div class="learning__RAMRButton learning__RAMRButton--play" '
                     'style="position:absolute;left:-9999px;top:0;width:50px;height:30px"></div>'
                     '<script>window.klik = 0; document.querySelector(".learning__RAMRButton--play")'
                     '.addEventListener("click", () => { window.klik++; });</script>')
    check("video: tombol putar di luar layar diabaikan (halaman tanpa video), tidak diklik",
          pelajaran.putar_video(page, 2000) is False and page.evaluate("() => window.klik") == 0)
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
    page = browser.new_page()  # situs asli (audio Lesson 3): saat selesai pemutar kembali ke 0, paused, ended false
    page.set_content(media_palsu("2") + video_palsu + (
        '<script>document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => {'
        ' if (window.main) return; window.main = true; window.t = 0.5;'
        ' setTimeout(() => { const v = document.querySelector("video"); window.main = false; window.t = 0; window.selesai = false;'
        ' v.dispatchEvent(new Event("ended")); }, 1200); });</script>'))
    check("video: pemutar yang kembali ke 0 saat selesai tetap terdeteksi lewat event 'ended'",
          pelajaran.putar_video(page, 4000) is True and page.evaluate("() => window.t") == 0)
    page.close()
    def audio_terpotong(t_akhir, jeda_ms=600):  # situs asli: tanpa 'ended'; dipotong sebelum akhir, sumber dimuat ulang
        return ('<script>document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => {'
                ' if (window.main) return; window.main = true; window.t = 0.5; const v = document.querySelector("video");'
                ' setTimeout(() => { window.t = ' + str(t_akhir) + '; v.dispatchEvent(new Event("timeupdate")); }, 300);'
                ' setTimeout(() => { window.t = 0; window.main = false; window.dur = NaN; v.dispatchEvent(new Event("emptied")); }, '
                + str(300 + jeda_ms) + '); });</script>')
    page = browser.new_page()
    page.set_content(media_palsu("18.44") + video_palsu + audio_terpotong(17.66))
    check("video: audio dipotong 0,8 dtk sebelum akhir tanpa 'ended' (situs asli) tetap terdeteksi selesai",
          pelajaran.putar_video(page, 4000) is True)
    page.close()
    page = browser.new_page()  # elemen audio yang SAMA dipakai ulang di halaman berikutnya (situs asli 14:17)
    page.set_content(media_palsu("18.44") + video_palsu + (
        '<script>window.fase = 0; document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => {'
        ' if (window.main) return; window.main = true; window.t = 0.5; window.fase++; const v = document.querySelector("video");'
        ' if (window.fase === 1) {'
        '  setTimeout(() => { window.t = 17.66; v.dispatchEvent(new Event("timeupdate")); }, 300);'
        '  setTimeout(() => { window.t = 0; window.main = false; window.dur = NaN; v.dispatchEvent(new Event("emptied")); window.dur = 18.44; }, 500);'
        ' } else {'
        '  setTimeout(() => { window.t = 0.7; v.dispatchEvent(new Event("timeupdate")); }, 300);'
        '  setTimeout(() => { window.t = 17.66; v.dispatchEvent(new Event("timeupdate")); }, 1000);'
        '  setTimeout(() => { window.t = 0; window.main = false; }, 1200); } });</script>'))
    pelajaran.putar_video(page, 4000)
    page.wait_for_function("() => !window.main", timeout=4000)
    mulai = time.time()
    pelajaran.putar_video(page, 4000)
    lama = time.time() - mulai
    check("video: pendengar dari halaman sebelumnya tidak menandai selesai di halaman baru (tunggu >= 0,8 dtk, bukan seketika)",
          lama >= 0.8)
    page.close()
    page = browser.new_page()  # media sudah berjalan (sisa halaman sebelumnya): jangan klik tombol putar (akan menjeda)
    page.set_content(media_palsu("2", "true") + video_palsu + (
        '<script>window.klik = 0; document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => { window.klik++; });'
        'setTimeout(() => { window.t = 2; window.selesai = true; }, 500);</script>'))
    check("video: media sudah berjalan -> tombol putar tidak diklik, tetap ditunggu sampai selesai",
          pelajaran.putar_video(page, 4000) is True and page.evaluate("() => window.klik") == 0)
    page.close()
    page = browser.new_page()  # audio yang sama dari halaman sebelumnya masih di ujung; Play tak berpengaruh sebelum diulang
    page.set_content('<script>window.main = false; window.t = 18.3; window.selesai = false; window.dur = 18.44;'
                     'const P = HTMLMediaElement.prototype;'
                     'Object.defineProperty(P, "paused", {get: () => !window.main});'
                     'Object.defineProperty(P, "currentTime", {get: () => window.t, set: (v) => { window.t = v; }});'
                     'Object.defineProperty(P, "duration", {get: () => window.dur});'
                     'Object.defineProperty(P, "ended", {get: () => window.selesai});</script>' + video_palsu + (
        '<script>document.querySelector(".learning__RAMRButton--play").addEventListener("click", () => {'
        ' if (window.main || window.t >= window.dur - 1) return; window.main = true; window.t = 0.5;'
        ' setTimeout(() => { window.t = 18; window.selesai = true; }, 800); });</script>'))
    check("video: media sisa di ujung diulang dari awal lalu diputar sampai selesai",
          pelajaran.putar_video(page, 4000) is True and page.evaluate("() => window.selesai") is True)
    page.close()
    page = browser.new_page()
    asli_tambahan = pelajaran.TAMBAHAN_TUNGGU_MEDIA
    pelajaran.TAMBAHAN_TUNGGU_MEDIA = 1
    page.set_content(media_palsu("10") + video_palsu + audio_terpotong(2.0))  # berhenti di 20%: bukan selesai
    check("video: berhenti jauh sebelum akhir lalu dimuat ulang -> TIDAK dianggap selesai (timeout, gagal tertutup)",
          raises(lambda: pelajaran.putar_video(page, 4000), Exception))
    pelajaran.TAMBAHAN_TUNGGU_MEDIA = asli_tambahan
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

    # --- Lapisan #EdoFrameBox: kartu Reminder sempat kosong (situs asli 11:36) ---
    lapisan = '<div id="EdoFrameBox" style="position:fixed;inset:0;background:#0006;z-index:9"></div>'
    tulis_kartu = ('<script>setTimeout(() => { document.getElementById("EdoFrameBox").innerHTML = '
                   '"<div style=\'background:#fff;margin:50px\'><h3>Reminder!</h3><p>You need to complete the '
                   'activities 2 and 3 to achieve progress in this step.</p></div>"; }, 800);</script>')
    page = browser.new_page()
    page.set_content('<p>halaman</p>' + lapisan + tulis_kartu)  # kartu kosong dulu, teks muncul 0,8 dtk kemudian
    check("lapisan: teks Reminder muncul belakangan -> ditunggu, lalu terbaca",
          pelajaran.overlay_menutupi(page) is True and pelajaran.tunggu_reminder(page) is True)
    page.close()
    page = browser.new_page()
    page.set_content('<p>halaman</p>' + lapisan)  # kartu tetap kosong
    asli = pelajaran.TUNGGU_REMINDER_DETIK
    pelajaran.TUNGGU_REMINDER_DETIK = 1
    check("lapisan: teks tak pernah muncul -> tidak dianggap Reminder (False), bukti frame dicatat",
          pelajaran.tunggu_reminder(page) is False)
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("lapisan: berurutan dengan lapisan tak dikenal -> berhenti, tidak mengklik apa pun",
          raises(lambda: pelajaran.kerjakan_berurutan(page, ring, 2, 2000), pelajaran.JenisSoalTidakDikenal))
    pelajaran.TUNGGU_REMINDER_DETIK = asli
    page.close()
    page = browser.new_page()
    page.set_content('<p>halaman biasa</p>')
    check("lapisan: tanpa lapisan -> overlay_menutupi False, tunggu_reminder False",
          pelajaran.overlay_menutupi(page) is False and pelajaran.tunggu_reminder(page) is False)
    page.close()

    # --- Status step yang terlambat diperbarui situs (bukti situs asli 12:31: inProgress, ±40 dtk kemudian done) ---
    def daftar_steps(status_practice, jadi_done_ms=None):
        skrip = ('<script>setTimeout(() => { document.getElementById("p").className = "progressBar__progress--done"; }, '
                 + str(jadi_done_ms) + ');</script>') if jadi_done_ms else ""
        return ('<div id="learning__dropDownListW_steps">'
                '<div class="learning__dropDownList_item"><span class="learning__dropDownList_itemNameText">1. Explore</span>'
                '<div class="progressBar__progress--done"></div></div>'
                '<div class="learning__dropDownList_item"><span class="learning__dropDownList_itemNameText">2. Practice</span>'
                f'<div id="p" class="progressBar__progress--{status_practice}"></div></div></div>' + skrip)
    page = browser.new_page()
    page.set_content(daftar_steps("inProgress", 1200))
    check("status step: inProgress lalu done 1,2 dtk kemudian -> ditunggu, True",
          pelajaran.tunggu_step_selesai(page, 1, detik=10) is True)
    page.close()
    page = browser.new_page()
    page.set_content(daftar_steps("inProgress"))
    check("status step: tetap inProgress -> False setelah batas tunggu (gagal tertutup)",
          pelajaran.tunggu_step_selesai(page, 1, detik=4) is False)
    page.close()
    page = browser.new_page()
    page.set_content(daftar_steps("done"))
    check("status step: sudah done -> True langsung", pelajaran.tunggu_step_selesai(page, 1, detik=4) is True)
    page.close()

    # --- Reminder basi: pager sudah --done tapi situs belum menyinkronkan (situs asli Lesson 2, 13:16) ---
    def reminder_basi(kelas3="learning__tasksNav_task--done learning__tasksNav_task--current", teks="the activity 2"):
        return ('<div class="learning__tasksNav_tasksW">'
                '<div class="learning__tasksNav_task learning__tasksNav_task--done">1</div>'
                '<div class="learning__tasksNav_task learning__tasksNav_task--done">2</div>'
                f'<div class="learning__tasksNav_task {kelas3}">3</div></div>'
                '<div id="isi">awal</div><a class="tasksBtnext" href="#">Next</a>'
                '<div id="rem" style="display:none"><p>You need to complete ' + teks + ' to achieve progress in this step.</p>'
                '<a id="c" href="#">Continue</a> <a id="s" href="#">Stay in this step</a></div>'
                '<script>let n = 0; window.klikPager = 0; window.lewat = false;'
                'document.querySelectorAll(".learning__tasksNav_task").forEach((e) => e.addEventListener("click", () => { window.klikPager++; }));'
                'document.querySelector(".tasksBtnext").addEventListener("click", (ev) => { ev.preventDefault(); n++;'
                ' if (n < 3) document.getElementById("rem").style.display = "block"; else document.getElementById("isi").textContent = "akhir"; });'
                'document.getElementById("s").addEventListener("click", (ev) => { ev.preventDefault(); document.getElementById("rem").style.display = "none"; });'
                'document.getElementById("c").addEventListener("click", (ev) => { ev.preventDefault(); window.lewat = true; });</script>')
    asli_jeda = pelajaran.JEDA_SINKRON_MS
    pelajaran.JEDA_SINKRON_MS = 200
    page = browser.new_page()
    page.set_content(reminder_basi())
    page.click(".tasksBtnext")  # Next pertama: Reminder menagih aktivitas 2 yang sudah --done
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    check("reminder basi (aktivitas sudah --done): tunggu sinkron, Next lagi -> lanjut; halaman tak dikerjakan ulang, Continue tak diklik",
          pelajaran.selesaikan_reminder(page, ring, 3000) == "lanjut" and page.inner_text("#isi") == "akhir"
          and page.evaluate("() => window.lewat") is False and page.evaluate("() => window.klikPager") == 0)  # 0: tak ada pindah halaman
    page.close()
    pelajaran.JEDA_SINKRON_MS = asli_jeda
    pelajaran.JEDA_SINKRON_MS = 200
    page = browser.new_page()
    page.set_content(reminder_basi(teks="all the activities"))  # varian tanpa nomor (situs asli 13:51)
    page.click(".tasksBtnext")
    check("reminder 'all the activities' (semua pager --done = basi): tunggu sinkron, Next lagi -> lanjut, Continue tak diklik",
          pelajaran.reminder_terlihat(page) is True
          and pelajaran.selesaikan_reminder(page, ring, 3000) == "lanjut" and page.inner_text("#isi") == "akhir"
          and page.evaluate("() => window.lewat") is False)
    page.close()
    pelajaran.JEDA_SINKRON_MS = asli_jeda
    def tahan_pindah(teks):  # klik "pindah" ditahan Reminder; Continue baru membuat perpindahan terjadi
        return ('<div id="EdoFrameBox" style="position:fixed;inset:0;background:#0006;z-index:9">'
                '<div style="background:#fff;margin:50px"><h3>Reminder!</h3><p>' + teks + '</p>'
                '<a id="c" href="#">Continue</a> <a id="s" href="#">Stay in this step</a></div></div>'
                '<script>window.pindah = false; window.klikC = 0;'
                'document.getElementById("c").addEventListener("click", (e) => { e.preventDefault(); window.klikC++; window.pindah = true;'
                ' document.getElementById("EdoFrameBox").remove(); });</script>')
    page = browser.new_page()
    page.set_content(tahan_pindah("You need to complete all the activities to achieve progress in this step."))
    pelajaran.lepas_reminder_pindah(page, lambda: page.evaluate("() => window.pindah === true"), detik=5)
    check("pindah ditahan Reminder 'all the activities': Continue diklik sekali, perpindahan terjadi",
          page.evaluate("() => window.klikC") == 1 and page.evaluate("() => window.pindah") is True)
    page.close()
    page = browser.new_page()
    page.set_content(tahan_pindah("Sesuatu yang lain sama sekali."))
    check("pindah ditahan Reminder bertulisan tak dikenal -> berhenti, Continue tidak diklik",
          raises(lambda: pelajaran.lepas_reminder_pindah(page, lambda: page.evaluate("() => window.pindah === true"), detik=5),
                 pelajaran.JenisSoalTidakDikenal) and page.evaluate("() => window.klikC") == 0)
    page.close()
    page = browser.new_page()
    page.set_content('<p>tanpa reminder</p><script>window.pindah = true;</script>')
    pelajaran.lepas_reminder_pindah(page, lambda: page.evaluate("() => window.pindah === true"), detik=5)
    check("pindah tanpa Reminder: langsung kembali", True)
    page.close()
    page = browser.new_page()  # sisa jalan sebelumnya: Reminder sudah terbuka sebelum bot mengklik apa pun (situs asli 14:06)
    page.set_content(tahan_pindah("You need to complete all the activities to achieve progress in this step."))
    pelajaran.tutup_reminder_terbuka(page)
    check("reminder sudah terbuka sebelum navigasi -> dibersihkan (Continue sekali)",
          page.evaluate("() => window.klikC") == 1 and not pelajaran.reminder_terlihat(page))
    page.close()
    page = browser.new_page()
    page.set_content('<p>bersih</p>')
    pelajaran.tutup_reminder_terbuka(page)
    check("tutup_reminder_terbuka tanpa Reminder: tidak melakukan apa pun", pelajaran.reminder_terlihat(page) is False)
    page.close()
    page = browser.new_page()
    page.set_content(reminder_basi())
    pelajaran.ke_halaman(page, 3, 3000)
    check("ke_halaman: sudah di halaman itu (--current) -> tidak mengklik pager",
          page.evaluate("() => window.klikPager") == 0)
    page.close()

    # --- Soal menulis prWriting (potongan HTML meniru rekaman: TinyMCE di iframe, Done, modal "Oops") ---
    def halaman_tulis(tolak=False):
        return ('<div class="learning__headerIW">Type your answer in the box and click Done.</div>'
                '<div class="prWriting__practice"><div class="prWriting__editorW">'
                '<span class="prWriting__editorWords">0</span>'
                '<iframe id="mce_0_ifr" style="width:300px;height:100px" srcdoc=\'<body id="tinymce" contenteditable="true"></body>\'></iframe>'
                '<span class="prWriting__action prWriting__action--submit prWriting__action--disabled">Done</span>'
                '</div></div><div class="prWriting__validationAlertBtn" style="display:none">OK</div>'
                '<script>const f = document.getElementById("mce_0_ifr"), done = document.querySelector(".prWriting__action--submit");'
                'const tolak = ' + ("true" if tolak else "false") + ';'
                '(function pasang() { const b = f.contentDocument && f.contentDocument.body;'
                ' if (!b || b.id !== "tinymce") { setTimeout(pasang, 50); return; }'
                ' b.addEventListener("input", () => { const n = b.innerText.trim().split(/\\s+/).filter(Boolean).length;'
                '  document.querySelector(".prWriting__editorWords").textContent = n;'
                '  done.classList.toggle("prWriting__action--disabled", n === 0); });'
                ' done.addEventListener("click", () => { const n = +document.querySelector(".prWriting__editorWords").textContent;'
                '  if (tolak || n < 5) document.querySelector(".prWriting__validationAlertBtn").style.display = "block";'
                '  else b.setAttribute("contenteditable", "false"); }); })();</script>')
    page = browser.new_page()
    page.set_content(halaman_tulis())
    ring = {"halaman": 0, "tak_terverifikasi": 0}
    pelajaran.kerjakan_halaman(page, ring, 6000)  # instruksi "Type ..." tidak lagi menghentikan bot di halaman menulis
    check("menulis: kalimat Inggris >= 5 kata diketik, Done diklik, editor terkunci",
          page.frame_locator("#mce_0_ifr").locator("body#tinymce").get_attribute("contenteditable") == "false"
          and int(page.inner_text(".prWriting__editorWords")) >= pelajaran.MIN_KATA_TULISAN
          and page.locator(".prWriting__validationAlertBtn").is_hidden())
    check("menulis: sudah terkunci -> tidak diketik ulang", pelajaran.isi_tulisan(page, 3000) is True)
    page.close()
    page = browser.new_page()
    page.set_content('<p>bukan halaman menulis</p>')
    check("menulis: tanpa area prWriting -> False", pelajaran.isi_tulisan(page, 2000) is False)
    page.close()
    page = browser.new_page()
    page.set_content(halaman_tulis(tolak=True))  # situs menolak: modal Oops muncul, editor tak terkunci
    check("menulis: Done ditolak (modal) -> berhenti, modal tak ditutup diam-diam",
          raises(lambda: pelajaran.isi_tulisan(page, 3000), pelajaran.JenisSoalTidakDikenal)
          and page.locator(".prWriting__validationAlertBtn").is_visible())
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

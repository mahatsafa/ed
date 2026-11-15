"""Fungsi bot per elemen tugas. Satu fungsi = satu persyaratan di panduan.

Selector di bawah untuk mock.html. Untuk situs asli, selector diganti
setelah HTML elemennya didapat.
"""
from playwright.sync_api import expect

from helpers import TIMEOUT_MS, click, periksa, setup_logger, wait_visible

MAX_TEKS = 500  # batas panjang teks yang boleh diisikan bot


def putar_video(page, timeout=TIMEOUT_MS):
    """Klik video lalu pastikan benar-benar berjalan (tidak berhenti, waktu maju)."""
    video = page.locator("#video")
    wait_visible(page, video, "video", timeout)
    click(page, video, "video", timeout)
    periksa(page, "video_terputar", lambda: page.wait_for_function(
        "() => { const v = document.querySelector('#video');"
        " return !v.paused && v.currentTime > 0; }", timeout=timeout))


def pilih_jawaban(page, pilihan="b", timeout=TIMEOUT_MS):
    """Pilih satu jawaban, submit, lalu pastikan 'Completed task' muncul tanpa reminder."""
    click(page, page.locator(f"input[name=answer][value={pilihan}]"), f"jawaban_{pilihan}", timeout)
    click(page, page.locator("#btn-submit"), "tombol_submit", timeout)
    periksa(page, "completed_task_muncul",
            lambda: expect(page.locator("#completed")).to_be_visible(timeout=timeout))
    periksa(page, "tidak_ada_reminder",
            lambda: expect(page.locator("#reminder")).to_be_hidden(timeout=timeout))


def isi_huruf_kosong(page, timeout=TIMEOUT_MS):
    """Klik pilihan kata satu per satu sampai semua kotak kosong terisi."""
    jumlah_kotak = page.locator(".blank").count()
    kata = page.locator(".word")
    jumlah_kata = kata.count()
    if jumlah_kotak == 0 or jumlah_kata == 0:  # gagal tertutup: jangan menebak
        raise RuntimeError("Kotak kosong atau pilihan kata tidak ditemukan.")
    for i in range(jumlah_kotak):  # batas atas = jumlah kotak, tidak bisa berputar terus
        click(page, kata.nth(i % jumlah_kata), f"kata_untuk_kotak_{i + 1}", timeout)
        periksa(page, f"kotak_{i + 1}_terisi", lambda i=i: expect(
            page.locator("#blank-status")).to_have_text(str(i + 1), timeout=timeout))


def isi_teks(page, timeout=TIMEOUT_MS):
    """Salin teks pertanyaan ke kolom teks, lalu pastikan isinya sama."""
    pertanyaan = page.locator("#question-text").inner_text(timeout=timeout).strip()
    if not pertanyaan or len(pertanyaan) > MAX_TEKS:
        raise RuntimeError("Teks pertanyaan kosong atau terlalu panjang.")
    setup_logger().info("Isi kolom teks (%d karakter)", len(pertanyaan))
    kolom = page.locator("#text-answer")
    kolom.fill(pertanyaan, timeout=timeout)
    periksa(page, "teks_terisi",
            lambda: expect(kolom).to_have_value(pertanyaan, timeout=timeout))


def klik_mikrofon(page, timeout=TIMEOUT_MS):
    """Klik tombol mikrofon lalu pastikan halaman mencatat klik."""
    click(page, page.locator("#btn-mic"), "tombol_mikrofon", timeout)
    periksa(page, "mikrofon_diklik", lambda: expect(
        page.locator("#mic-status")).to_have_text("mikrofon diklik", timeout=timeout))


def klik_start(page, timeout=TIMEOUT_MS):
    """Klik teks dulu (mengaktifkan Start), lalu klik tombol Start."""
    click(page, page.locator("#start-text"), "teks_pengaktif_start", timeout)
    periksa(page, "start_aktif", lambda: expect(
        page.locator("#btn-start")).to_be_enabled(timeout=timeout))
    click(page, page.locator("#btn-start"), "tombol_start", timeout)
    periksa(page, "start_dimulai", lambda: expect(
        page.locator("#start-status")).to_have_text("sudah dimulai", timeout=timeout))


def klik_header(page, timeout=TIMEOUT_MS):
    """Klik dua tombol di header satu per satu."""
    for n in (1, 2):
        click(page, page.locator(f"#header-btn-{n}"), f"tombol_header_{n}", timeout)
        periksa(page, f"header_{n}_diklik", lambda n=n: expect(
            page.locator("#header-status")).to_have_text(f"header {n} diklik", timeout=timeout))


def jalankan_semua(page):
    """Urutan sesuai panduan: video, jawaban, huruf kosong, teks, mikrofon, start, header."""
    log = setup_logger()
    for langkah in (putar_video, pilih_jawaban, isi_huruf_kosong, isi_teks,
                    klik_mikrofon, klik_start, klik_header):
        log.info("== Langkah: %s", langkah.__name__)
        langkah(page)
    log.info("Semua langkah selesai.")

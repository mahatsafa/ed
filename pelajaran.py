"""Pengulang pelajaran untuk situs asli: kerjakan satu halaman soal, klik Next, ulangi.

Aturan keselamatan:
- Berhenti kalau jenis soal tidak dikenal (tidak menebak dan tidak melompati soal).
- Berhenti di batas halaman (maks) dan saat Next tidak mengubah halaman.
- Tidak pernah menyentuh "See Answer" (kunci jawaban); jawaban dipilih tanpa membaca kunci.
"""
import re

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import expect

from helpers import TIMEOUT_MS, click, periksa, screenshot_on_fail, setup_logger

SEL = {
    "video_overlay": ".learning__RAMRButton--play",  # tombol putar yang menutupi <video>
    "video_kustom": "#CTrackerPlayBtn",
    "modal": "ngb-modal-window",
    "modal_tutup": "button.close, [aria-label=Close], .close",
    "video": "video",
    "radio": "input.layout__radio",
    "dropdown": "select",
    "cloze_kotak": ".prCLZ__regContainer .dndZone",  # kotak kosong
    "cloze_kata": ".prCLZ__wordsBankWrapper .dnditem",  # kata di bank
    "kata_terisi": ".dnditem",
    "start": ".speakingInteractButtonWrapper a.continue",
    "start_nonaktif": ".speakingInteractButtonWrapper .continueWrapper.disable",
    "cek": "#CheckAnswer",
    "next": "a.tasksBtnext",
    "selesai": ".learning__tasksNav_task--done",
}
HEADER_ASLI = ("settingsMenu__dictionary", "settingsMenu__help")  # dua tombol header yang diklik
MAX_HALAMAN = 30  # batas halaman per jalan
# Instruksi soal yang belum didukung bot: berhenti, jangan lompat ke Next tanpa menjawab.
TIDAK_DIDUKUNG = re.compile(r"^\s*(Drag|Type|Write|Fill|Match|Put|Record|Say|Speak|Order)\b")
MEDIA_JALAN = ("() => [...document.querySelectorAll('video,audio')]"
               ".some(m => !m.paused && m.currentTime > 0)")
TEKS_HALAMAN = "() => document.body.innerText.replace(/\\d/g, '')"  # angka dibuang (waktu video)


class JenisSoalTidakDikenal(RuntimeError):
    """Halaman soal tidak punya elemen yang dikenal bot."""


def tutup_modal(page, timeout=TIMEOUT_MS):
    """Tutup modal (mis. Video Tutorials dari menu Help) kalau terbuka: Escape, lalu tombol tutup."""
    modal = page.locator(SEL["modal"])
    if not modal.count():
        return
    setup_logger().info("Modal terbuka, ditutup")
    page.keyboard.press("Escape")
    try:
        expect(modal).to_have_count(0, timeout=min(timeout, 3000))
    except AssertionError:
        click(page, modal.locator(SEL["modal_tutup"]).first, "tutup_modal", timeout)
        periksa(page, "modal_tertutup", lambda: expect(modal).to_have_count(0, timeout=timeout))


def klik_header(page, timeout=TIMEOUT_MS):
    """Klik dua tombol header, pastikan menunya terbuka, lalu tutup modal yang muncul."""
    for id_ in HEADER_ASLI:
        tombol = page.locator(f"#{id_}")
        click(page, tombol, id_, timeout)
        periksa(page, f"{id_}_terbuka", lambda t=tombol: expect(t).to_have_class(
            re.compile(r"settingsMenu__listCat--open"), timeout=timeout))
        tutup_modal(page, timeout)


def putar_video(page, timeout=TIMEOUT_MS):
    overlay = page.locator(SEL["video_overlay"])
    kustom = page.locator(SEL["video_kustom"])
    video = page.locator(SEL["video"]).first
    if overlay.count() and overlay.first.is_visible():
        click(page, overlay.first, "video_tombol_putar", timeout)
    elif kustom.count() and kustom.is_visible():
        click(page, kustom, "video_tombol_putar", timeout)
    elif video.count() and video.is_visible():
        if video.evaluate("v => v.paused"):  # jangan klik kalau sudah berjalan (bisa menjeda)
            click(page, video, "video", timeout)
    else:
        return False
    periksa(page, "video_terputar", lambda: page.wait_for_function(MEDIA_JALAN, timeout=timeout))
    return True


def pilih_radio(page, timeout=TIMEOUT_MS):
    radios = page.locator(SEL["radio"])
    if not radios.count():
        return False
    pertama = radios.first
    click(page, pertama, "pilihan_jawaban_1", timeout)
    periksa(page, "jawaban_terpilih", lambda: expect(pertama).to_be_checked(timeout=timeout))
    return True


def isi_dropdown(page, timeout=TIMEOUT_MS):
    daftar = page.locator(SEL["dropdown"])
    jumlah = daftar.count()
    if not jumlah:
        return False
    for n in range(jumlah):  # batas atas = jumlah dropdown
        satu = daftar.nth(n)
        if not satu.is_visible():
            continue
        satu.select_option(index=1, timeout=timeout)
        periksa(page, f"dropdown_{n + 1}_terisi",
                lambda s=satu: expect(s).not_to_have_value("", timeout=timeout))
    return True


def seret(page, sumber, tujuan, nama, timeout=TIMEOUT_MS):
    """Seret dengan mouse bertahap (Dragula butuh beberapa gerakan mouse, bukan satu lompatan)."""
    setup_logger().info("Seret: %s", nama)
    tujuan.scroll_into_view_if_needed(timeout=timeout)
    sumber.scroll_into_view_if_needed(timeout=timeout)
    a, b = sumber.bounding_box(), tujuan.bounding_box()
    if not a or not b:
        raise RuntimeError(f"Posisi {nama} tidak terbaca.")
    ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
    bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    page.mouse.move(ax, ay)
    page.mouse.down()
    page.mouse.move(ax + 8, ay + 8, steps=4)
    page.mouse.move(bx, by, steps=15)
    page.mouse.up()


def isi_cloze(page, timeout=TIMEOUT_MS):
    """Isi tiap kotak kosong dengan kata dari bank (urutan bank; tanpa membaca kunci)."""
    kotak = page.locator(SEL["cloze_kotak"])
    jumlah = kotak.count()
    if not jumlah:
        return False
    for k in range(jumlah):  # batas atas = jumlah kotak
        satu = kotak.nth(k)
        if satu.locator(SEL["kata_terisi"]).count():
            continue  # sudah terisi
        kata = page.locator(SEL["cloze_kata"])
        if not kata.count():
            screenshot_on_fail(page, "cloze_kata_habis")
            raise RuntimeError("Kata di bank habis sebelum semua kotak terisi.")
        seret(page, kata.first, satu, f"kata_ke_kotak_{k + 1}", timeout)
        periksa(page, f"kotak_{k + 1}_terisi", lambda s=satu: expect(
            s.locator(SEL["kata_terisi"])).to_have_count(1, timeout=timeout))
    return True


def klik_start(page, timeout=TIMEOUT_MS):
    start = page.locator(SEL["start"])
    if not start.count():
        return False
    periksa(page, "start_aktif", lambda: expect(
        page.locator(SEL["start_nonaktif"])).to_have_count(0, timeout=timeout))
    click(page, start, "tombol_start", timeout)
    return True


def cek_jawaban(page, sebelum, ringkasan, timeout=TIMEOUT_MS):
    """Klik Check Answer lalu lihat apakah jumlah tugas selesai bertambah."""
    log = setup_logger()
    click(page, page.locator(SEL["cek"]), "check_answer", timeout)
    try:
        page.wait_for_function("([s, n]) => document.querySelectorAll(s).length > n",
                               arg=[SEL["selesai"], sebelum], timeout=min(timeout, 8000))
        log.info("OK: tugas tercatat selesai")
    except PWTimeout:  # penanda selesai belum terbukti; catat, jangan pura-pura berhasil
        ringkasan["tak_terverifikasi"] += 1
        log.warning("Tugas TIDAK terbukti selesai setelah Check Answer")
        screenshot_on_fail(page, "cek_tak_terverifikasi")


def kerjakan_halaman(page, ringkasan, timeout=TIMEOUT_MS):
    log = setup_logger()
    tak_didukung = page.get_by_text(TIDAK_DIDUKUNG)
    if tak_didukung.count():  # ada instruksi (mis. "Drag ...") yang belum bisa dikerjakan bot
        teks = tak_didukung.first.inner_text()[:60]
        screenshot_on_fail(page, "instruksi_belum_didukung")
        raise JenisSoalTidakDikenal(f"Instruksi soal belum didukung: {teks!r}")
    sebelum = page.locator(SEL["selesai"]).count()
    dikerjakan, perlu_cek = [], False
    if putar_video(page, timeout):
        dikerjakan.append("video")
    if pilih_radio(page, timeout):
        dikerjakan.append("pilihan")
        perlu_cek = True
    if isi_dropdown(page, timeout):
        dikerjakan.append("dropdown")
        perlu_cek = True
    if isi_cloze(page, timeout):
        dikerjakan.append("isian kata")
        perlu_cek = True
    if klik_start(page, timeout):
        dikerjakan.append("start")
    if not dikerjakan:
        screenshot_on_fail(page, "jenis_soal_tidak_dikenal")
        raise JenisSoalTidakDikenal("Halaman ini tidak punya elemen yang dikenal bot.")
    log.info("Halaman dikerjakan: %s", ", ".join(dikerjakan))
    if perlu_cek:
        cek_jawaban(page, sebelum, ringkasan, timeout)


def lanjut(page, timeout=TIMEOUT_MS):
    """Klik Next. True kalau halaman berganti, False kalau tidak (pelajaran selesai)."""
    tombol = page.locator(SEL["next"])
    if not tombol.count() or not tombol.is_visible():
        return False
    sebelum = page.evaluate(TEKS_HALAMAN)
    click(page, tombol, "next", timeout)
    try:
        page.wait_for_function("(s) => document.body.innerText.replace(/\\d/g, '') !== s",
                               arg=sebelum, timeout=min(timeout, 6000))
    except PWTimeout:
        return False
    return True


def jalankan_pelajaran(page, maks=MAX_HALAMAN, timeout=TIMEOUT_MS):
    log = setup_logger()
    ringkasan = {"halaman": 0, "tak_terverifikasi": 0}
    while ringkasan["halaman"] < maks:
        ringkasan["halaman"] += 1
        log.info("== Halaman %d", ringkasan["halaman"])
        kerjakan_halaman(page, ringkasan, timeout)
        if not lanjut(page, timeout):
            log.info("Next tidak mengubah halaman: pelajaran selesai.")
            break
    else:
        log.warning("Batas %d halaman tercapai, berhenti.", maks)
    klik_header(page, timeout)  # terakhir, supaya modal dari menu Help tidak menghalangi soal
    log.info("Ringkasan: %s", ringkasan)
    return ringkasan

"""Pengulang pelajaran untuk situs asli: kerjakan satu halaman soal, klik Next, ulangi.

Aturan keselamatan:
- Berhenti kalau jenis soal tidak dikenal (tidak menebak dan tidak melompati soal).
- Berhenti di batas halaman (maks) dan saat Next tidak mengubah halaman.
- Tidak pernah menyentuh "See Answer" (kunci jawaban); jawaban dipilih tanpa membaca kunci.
"""
import re

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import expect

from helpers import TIMEOUT_MS, click, periksa, screenshot_on_fail, setup_logger, wait_visible

SEL = {
    "instruksi": ".learning__headerIW",  # kalimat instruksi di atas soal
    "video_overlay": ".learning__RAMRButton--play",  # tombol putar yang menutupi <video>
    "video_kustom": "#CTrackerPlayBtn",
    "modal": "ngb-modal-window",
    "modal_tutup": "button.close, [aria-label=Close], .close",
    "video": "video",
    "radio": "input.layout__radio",
    "mcq_set": ".prMCQ__qaSet",  # satu pertanyaan pilihan ganda (halaman bisa punya beberapa)
    "dropdown": ".prFITB__DDLOptionsW",  # dropdown kustom (bukan <select>)
    "dd_terpilih": ".DDLOptions__selected",
    "dd_daftar": ".DDLOptions__list",
    "dd_item": ".DDLOptions__listItem",
    "cloze_kotak": ".prCLZ__regContainer .dndZone",  # kotak kosong
    "cloze_kata": ".prCLZ__wordsBankWrapper .dnditem",  # kata di bank
    "kata_terisi": ".dnditem",
    "start": ".speakingInteractButtonWrapper a.continue",
    "start_nonaktif": ".speakingInteractButtonWrapper .continueWrapper.disable",
    "cek": "#CheckAnswer",
    "next": "a.tasksBtnext",
    "selesai": ".learning__tasksNav_task--done",
    "kartu_unit": ".home__unitIW",  # kartu unit di dashboard; teks "Completed!" kalau unit selesai
    "rumah": "#sitemenu__itemHome",  # ikon rumah di header area belajar
    "intro": ".learning__tasksNav_pager_intro.learning__tasksNav_task--current",  # layar intro step
    "item_daftar": ".learning__dropDownList_item",
}
# Step yang dikerjakan manual oleh pemilik akun (bernilai); bot tidak menyentuhnya.
STEP_MANUAL = re.compile(r"\b(Test|Quiz|Exam)\b", re.I)
MAX_UNIT = 60  # batas unit yang dicoba per jalan
MAX_STEP = 400  # batas (lesson, step) yang dikerjakan per jalan
MAX_TOTAL_HALAMAN = 3000  # batas halaman soal per jalan
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
    """Jawab tiap pertanyaan pilihan ganda dengan opsi pertama (klik label; input asli bisa tersembunyi)."""
    radios = page.locator(SEL["radio"])
    if not radios.count():
        return False
    himpunan = page.locator(SEL["mcq_set"])
    if radios.count() != page.locator(f"{SEL['mcq_set']} {SEL['radio']}").count():
        screenshot_on_fail(page, "radio_di_luar_set")  # radio yang tak bisa dikelompokkan: jangan menebak
        raise JenisSoalTidakDikenal("Ada radio di luar .prMCQ__qaSet; pengelompokan pertanyaan tak jelas.")
    for n in range(himpunan.count()):  # batas atas = jumlah pertanyaan
        pertama = himpunan.nth(n).locator(SEL["radio"]).first
        id_ = pertama.get_attribute("id", timeout=timeout)
        if not id_:
            screenshot_on_fail(page, f"radio_tanpa_id_{n + 1}")
            raise JenisSoalTidakDikenal(f"Radio pertanyaan {n + 1} tanpa id; label tak bisa dicari.")
        click(page, himpunan.nth(n).locator(f'label[for="{id_}"]'), f"pertanyaan_{n + 1}_pilihan_1", timeout)
        periksa(page, f"pertanyaan_{n + 1}_terjawab", lambda r=pertama: expect(r).to_be_checked(timeout=timeout))
    return True


def isi_dropdown(page, timeout=TIMEOUT_MS):
    """Isi tiap dropdown kustom dengan item pertama di daftarnya (tanpa membaca kunci)."""
    daftar = page.locator(SEL["dropdown"])
    jumlah = daftar.count()
    dikerjakan = False
    for n in range(jumlah):  # batas atas = jumlah dropdown
        satu = daftar.nth(n)
        if not satu.is_visible():
            continue
        terpilih = satu.locator(SEL["dd_terpilih"])
        if terpilih.inner_text().strip():
            dikerjakan = True  # sudah terisi
            continue
        click(page, terpilih, f"dropdown_{n + 1}_buka", timeout)
        wait_visible(page, satu.locator(SEL["dd_daftar"]), f"dropdown_{n + 1}_daftar", timeout)
        click(page, satu.locator(SEL["dd_item"]).first, f"dropdown_{n + 1}_item_1", timeout)
        periksa(page, f"dropdown_{n + 1}_terisi",
                lambda t=terpilih: expect(t).not_to_have_text("", timeout=timeout))
        periksa(page, f"dropdown_{n + 1}_daftar_tertutup", lambda s=satu: expect(
            s.locator(SEL["dd_daftar"])).to_have_count(0, timeout=timeout))
        dikerjakan = True
    return dikerjakan


STABIL_JS = """([ambil, perlu]) => {
  const t = eval(ambil)();
  const k = window.__botStabil;
  window.__botStabil = {t: t, n: k && k.t === t ? k.n + 1 : 0};
  return window.__botStabil.n >= perlu;
}"""


def tunggu_stabil(page, jeda_ms=400, perlu=2, maks_baca=15):
    """Tunggu teks halaman tidak berubah selama `perlu` pembacaan berturut-turut (render selesai).
    Polling di sisi halaman (tanpa sleep di Python); batas atas = maks_baca x jeda_ms, lewat batas = lanjut."""
    page.evaluate("() => { window.__botStabil = null; }")
    try:
        page.wait_for_function(STABIL_JS, arg=[TEKS_HALAMAN, perlu], polling=jeda_ms,
                               timeout=jeda_ms * maks_baca)
    except PWTimeout:
        setup_logger().warning("Halaman belum stabil setelah %d ms, lanjut.", jeda_ms * maks_baca)


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


def isi_seret(page, sel_kotak, sel_kata, nama, timeout=TIMEOUT_MS):
    """Isi tiap kotak kosong dengan kata dari bank (urutan bank; tanpa membaca kunci)."""
    kotak = page.locator(sel_kotak)
    jumlah = kotak.count()
    if not jumlah:
        return False
    for k in range(jumlah):  # batas atas = jumlah kotak
        satu = kotak.nth(k)
        if satu.locator(SEL["kata_terisi"]).count():
            continue  # sudah terisi
        kata = page.locator(sel_kata)
        if not kata.count():
            screenshot_on_fail(page, f"{nama}_kata_habis")
            raise RuntimeError("Kata di bank habis sebelum semua kotak terisi.")
        seret(page, kata.first, satu, f"{nama}_kata_ke_kotak_{k + 1}", timeout)
        periksa(page, f"{nama}_kotak_{k + 1}_terisi", lambda s=satu: expect(
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
    instruksi = page.locator(SEL["instruksi"])
    teks = instruksi.first.inner_text().strip() if instruksi.count() else ""
    if TIDAK_DIDUKUNG.match(teks):  # instruksi (mis. "Drag ...") yang belum bisa dikerjakan bot
        screenshot_on_fail(page, "instruksi_belum_didukung")
        raise JenisSoalTidakDikenal(f"Instruksi soal belum didukung: {teks[:60]!r}")
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
    if isi_seret(page, SEL["cloze_kotak"], SEL["cloze_kata"], "cloze", timeout):
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


def kerjakan_berurutan(page, ringkasan, maks, timeout=TIMEOUT_MS):
    """Kerjakan halaman satu per satu lalu Next. Kembalikan alasan berhenti:
    "habis" (Next tidak mengubah halaman), "test" (step Test, dikerjakan manual), "batas"."""
    log = setup_logger()
    mulai = ringkasan["halaman"]
    while ringkasan["halaman"] - mulai < maks:
        ringkasan["halaman"] += 1
        log.info("== Halaman %d", ringkasan["halaman"])
        tunggu_stabil(page)
        if sedang_test(page):
            ringkasan["halaman"] -= 1
            log.info("Step Test (dikerjakan manual): berhenti di sini, tidak disentuh.")
            return "test"
        if page.locator(SEL["intro"]).count():
            log.info("Layar intro step: langsung Next")
        else:
            kerjakan_halaman(page, ringkasan, timeout)
        if not lanjut(page, timeout):
            log.info("Next tidak mengubah halaman.")
            return "habis"
    log.warning("Batas %d halaman tercapai, berhenti.", maks)
    return "batas"


def ada_area(page):
    return page.locator("#learning__dropDownListTitleW_lessons").count() > 0


def ada_dashboard(page):
    return page.locator(SEL["kartu_unit"]).count() > 0


def judul(page, jenis):
    """Judul lesson/step yang sedang dibuka ("lessons" atau "steps"); kosong kalau tak terbaca."""
    el = page.locator(f"#learning__dropDownListTitleW_{jenis} .learning__dropDownListTitle")
    return (el.first.get_attribute("title", timeout=2000) or "").strip() if el.count() else ""


def sedang_test(page):
    """Di area belajar, step bernama Test/Quiz/Exam? Judul tak terbaca = anggap Test (gagal tertutup)."""
    if not ada_area(page):
        return False
    nama = judul(page, "steps")
    return not nama or bool(STEP_MANUAL.search(nama))


JS_DAFTAR = """(jenis) => [...document.querySelectorAll(
    `#learning__dropDownListW_${jenis} .learning__dropDownList_item`)].map(el => {
  const p = el.querySelector('[class*="progressBar__progress--"]');
  const m = p && p.className.match(/progressBar__progress--(done|inProgress|notStarted)\\b/);
  const n = el.querySelector('.learning__dropDownList_itemNameText') || el;
  return {nama: n.textContent.trim(), status: m ? m[1] : null,
          sekarang: el.classList.contains('learning__dropDownList_item--current')};
})"""


def baca_daftar(page, jenis, timeout=TIMEOUT_MS):
    """Daftar lesson/step beserta status (done/inProgress/notStarted). Status tak dikenal = berhenti."""
    try:  # daftar dirender belakangan (Angular): tunggu ada item dulu, jangan membaca daftar kosong
        page.locator(f"#learning__dropDownListW_{jenis} {SEL['item_daftar']}").first.wait_for(
            state="attached", timeout=timeout)
    except PWTimeout:
        pass  # kosong tetap ditolak di bawah, lengkap dengan screenshot
    hasil = page.evaluate(JS_DAFTAR, jenis)
    if not hasil or any(h["status"] is None for h in hasil):
        screenshot_on_fail(page, f"daftar_{jenis}_tak_terbaca")
        raise JenisSoalTidakDikenal(f"Daftar {jenis} kosong atau status progres tak terbaca.")
    return hasil


def pilih_item(page, jenis, indeks, timeout=TIMEOUT_MS):
    """Buka dropdown lesson/step, klik item ke-`indeks`, tunggu item itu jadi yang aktif."""
    daftar = page.locator(f"#learning__dropDownListW_{jenis}")
    item = daftar.locator(SEL["item_daftar"]).nth(indeks)
    if not daftar.is_visible():
        click(page, page.locator(f"#learning__dropDownListTitleW_{jenis}"), f"buka_daftar_{jenis}", timeout)
    wait_visible(page, item, f"item_{jenis}_{indeks + 1}", timeout)
    sudah_aktif = "--current" in (item.get_attribute("class") or "")
    if not sudah_aktif:
        click(page, item.locator(".learning__dropDownList_itemName"), f"pilih_{jenis}_{indeks + 1}", timeout)
        periksa(page, f"{jenis}_{indeks + 1}_aktif", lambda: expect(item).to_have_class(
            re.compile(r"--current"), timeout=timeout))
    if daftar.is_visible():  # daftar masih terbuka: tutup supaya tidak menutupi soal
        click(page, page.locator(f"#learning__dropDownListTitleW_{jenis}"), f"tutup_daftar_{jenis}", timeout)
    tunggu_stabil(page)


def cari_target(page, dilewati, timeout=TIMEOUT_MS):
    """Cari (lesson, indeks step, nama step) pertama yang belum selesai dan bukan step manual.
    Lesson yang hanya tersisa step manual dicatat di `dilewati` (per unit). Tidak ada = None."""
    for li, lesson in enumerate(baca_daftar(page, "lessons")):  # batas atas = jumlah lesson
        if lesson["status"] == "done" or lesson["nama"] in dilewati:
            continue
        pilih_item(page, "lessons", li, timeout)
        for si, step in enumerate(baca_daftar(page, "steps")):  # batas atas = jumlah step
            if step["status"] != "done" and not STEP_MANUAL.search(step["nama"]):
                return lesson["nama"], si, step["nama"]
        dilewati.add(lesson["nama"])
    return None


def buka_lesson_berikutnya(page, dilewati, dicoba, timeout=TIMEOUT_MS):
    """Dari area belajar: pilih lesson pertama yang belum selesai, lalu step pertama yang belum selesai
    (bukan Test), dan tunggu halaman pertamanya siap. None kalau unit ini habis."""
    log = setup_logger()
    target = cari_target(page, dilewati, timeout)
    if target is None:
        return None
    if target in dicoba:  # sudah pernah dikerjakan tapi status belum selesai: jangan berputar-putar
        screenshot_on_fail(page, "tidak_ada_kemajuan")
        raise RuntimeError(f"Tidak ada kemajuan: {target} dipilih lagi padahal sudah dikerjakan.")
    dicoba.add(target)
    lesson, si, step = target
    log.info("Target: lesson %r, step %r", lesson, step)
    pilih_item(page, "steps", si, timeout)
    return target


def buka_unit(page, unit_dicoba, timeout=TIMEOUT_MS):
    """Dari dashboard: klik unit pertama yang belum "Completed!" dan belum dicoba. False kalau tak ada."""
    kartu = page.locator(SEL["kartu_unit"])
    wait_visible(page, kartu.first, "kartu_unit", timeout)
    for n in range(min(kartu.count(), MAX_UNIT)):  # batas atas = jumlah kartu
        if n in unit_dicoba or "Completed!" in kartu.nth(n).inner_text():
            continue
        unit_dicoba.add(n)
        setup_logger().info("Buka unit ke-%d: %s", n + 1, kartu.nth(n).inner_text().replace("\n", " ")[:50])
        click(page, kartu.nth(n), f"kartu_unit_{n + 1}", timeout)
        wait_visible(page, page.locator("#learning__dropDownListTitleW_lessons"), "area_belajar", timeout)
        tunggu_stabil(page)
        return True
    return False


def kembali_ke_dashboard(page, timeout=TIMEOUT_MS):
    click(page, page.locator(SEL["rumah"]), "ikon_rumah", timeout)
    wait_visible(page, page.locator(SEL["kartu_unit"]).first, "dashboard", timeout)


def jalankan_pelajaran(page, timeout=TIMEOUT_MS, maks_halaman=MAX_TOTAL_HALAMAN):
    """Mulai dari dashboard (atau area belajar), kerjakan lesson demi lesson sampai semua unit
    selesai, kecuali step Test yang dikerjakan manual. Berhenti kalau ada jenis soal tak dikenal."""
    log = setup_logger()
    ringkasan = {"halaman": 0, "tak_terverifikasi": 0}
    unit_dicoba, langkah = set(), 0
    if not ada_dashboard(page) and not ada_area(page):
        screenshot_on_fail(page, "bukan_dashboard_atau_area")
        raise JenisSoalTidakDikenal(f"Bukan dashboard atau area belajar: {page.url.split('?')[0]}")
    while True:
        if ada_dashboard(page) and not buka_unit(page, unit_dicoba, timeout):
            log.info("Semua unit selesai (selain step Test).")
            break
        dilewati, dicoba = set(), set()  # nama lesson berulang antar unit, jadi dicatat per unit
        while True:
            langkah += 1
            if langkah > MAX_STEP or ringkasan["halaman"] >= maks_halaman:
                log.warning("Batas langkah/halaman tercapai, berhenti.")
                klik_header(page, timeout)
                return ringkasan
            if buka_lesson_berikutnya(page, dilewati, dicoba, timeout) is None:
                break
            kerjakan_berurutan(page, ringkasan, maks_halaman - ringkasan["halaman"], timeout)
        kembali_ke_dashboard(page, timeout)
    klik_header(page, timeout)  # terakhir, supaya modal dari menu Help tidak menghalangi soal
    log.info("Ringkasan: %s", ringkasan)
    return ringkasan

"""Pengulang pelajaran untuk situs asli: kerjakan satu halaman soal, klik Next, ulangi.

Aturan keselamatan:
- Berhenti kalau jenis soal tidak dikenal (tidak menebak dan tidak melompati soal).
- Berhenti di batas halaman (maks) dan saat Next tidak mengubah halaman.
- Tidak pernah menyentuh "See Answer" (kunci jawaban); jawaban dipilih tanpa membaca kunci.
"""
import re
from datetime import datetime

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import expect

from helpers import LOG_DIR, TIMEOUT_MS, click, periksa, screenshot_on_fail, setup_logger, wait_visible

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
    "cocok_kotak": ".prMT_T2T__regContainer .dndZone",  # kotak jawaban tiap baris pencocokan
    "cocok_kata": ".prMT_T2T__wordsBankWrapper .dnditem",  # kata di bank pencocokan
    "webrtc": ".answersWrapper.webRtc",  # soal dengan pengenalan suara (butuh mikrofon)
    "start": ".speakingInteractButtonWrapper a.continue",
    "start_nonaktif": ".speakingInteractButtonWrapper .continueWrapper.disable",
    "cek": "#CheckAnswer",
    "next": "a.tasksBtnext",
    "selesai": ".learning__tasksNav_task--done",
    "kartu_unit": ".home__unitIW",  # kartu unit di dashboard; teks "Completed!" kalau unit selesai
    "daftar_lesson_kartu": ".home__courseList",  # daftar lesson di kartu yang berbalik
    "lesson_kartu": "a.home__courseListItemLink:not(.home__courseListItemLink--locked)",
    "rumah": "#sitemenu__itemHome",  # ikon rumah di header area belajar
    "intro": ".learning__tasksNav_pager_intro.learning__tasksNav_task--current",  # layar intro step
    "item_daftar": ".learning__dropDownList_item",
}
# Step yang dikerjakan manual oleh pemilik akun (bernilai); bot tidak menyentuhnya.
STEP_MANUAL = re.compile(r"\b(Test|Quiz|Exam)\b", re.I)
MAX_UNIT = 60  # batas unit yang dicoba per jalan
TUNGGU_AREA_MS = 45_000  # halaman area belajar adalah muat-ulang penuh (learningArea.html), bisa lambat
TUNGGU_DASHBOARD_MS = 30_000
MAX_STEP = 400  # batas (lesson, step) yang dikerjakan per jalan
MAX_TOTAL_HALAMAN = 3000  # batas halaman soal per jalan
HEADER_ASLI = ("settingsMenu__dictionary", "settingsMenu__help")  # dua tombol header yang diklik
MAX_HALAMAN = 30  # batas halaman per jalan
# Instruksi soal yang belum didukung bot: berhenti, jangan lompat ke Next tanpa menjawab.
# (Drag dan Match sudah punya handler: cloze dan pencocokan.)
TIDAK_DIDUKUNG = re.compile(r"^\s*(Type|Write|Fill|Put|Record|Say|Speak|Order)\b")
# Isian teks bebas yang terlihat di luar panel Dictionary: belum ada handler.
JS_ISIAN_TEKS = """() => [...document.querySelectorAll('textarea, [contenteditable=true], input[type=text]')]
    .some(e => !e.closest('#DictionaryPanelContainer') && e.offsetParent !== null)"""
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


def elemen_belum_didukung(page):
    """Nama elemen soal tanpa handler (suara, isian teks) kalau ada di halaman; kalau tidak, None."""
    if page.locator(SEL["webrtc"]).count():
        return "suara (webRtc)"
    if page.evaluate(JS_ISIAN_TEKS):
        return "isian teks"
    return None


JS_HALAMAN_BACAAN = """(sel) => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const q = (x) => [...document.querySelectorAll(x)].filter(vis);
  const kontrol = q('input, select, textarea, [contenteditable], .dndZone, .dnditem, button')
    .filter((e) => !e.closest('#DictionaryPanelContainer'));
  return q(sel.cek).length === 0 && q(sel.next).length > 0 && kontrol.length === 0;
}"""


def halaman_bacaan(page):
    """True kalau halaman hanya bacaan: Next terlihat, tetapi tidak ada Check Answer maupun kontrol isian
    yang terlihat. Cukup Next sekali; situs mencatatnya sebagai dikerjakan. Ragu = False (bot berhenti)."""
    return page.evaluate(JS_HALAMAN_BACAAN, {"cek": SEL["cek"], "next": SEL["next"]})


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
    if TIDAK_DIDUKUNG.match(teks):  # instruksi (mis. "Type ...") yang belum bisa dikerjakan bot
        screenshot_on_fail(page, "instruksi_belum_didukung")
        raise JenisSoalTidakDikenal(f"Instruksi soal belum didukung: {teks[:60]!r}")
    belum = elemen_belum_didukung(page)  # sebelum mengklik apa pun
    if belum:
        screenshot_on_fail(page, "elemen_belum_didukung")
        raise JenisSoalTidakDikenal(f"Elemen soal belum didukung: {belum}")
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
    if isi_seret(page, SEL["cocok_kotak"], SEL["cocok_kata"], "pencocokan", timeout):
        dikerjakan.append("pencocokan")
        perlu_cek = True
    if klik_start(page, timeout):
        dikerjakan.append("start")
    if not dikerjakan and halaman_bacaan(page):
        log.info("Halaman bacaan (tanpa soal): cukup Next")
        return
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


def simpan_html_daftar(page, jenis):
    """Simpan HTML daftar lesson/step ke logs/ (baca saja) sebagai bukti saat pembacaan gagal."""
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_daftar_{jenis}.html"
    html = page.evaluate("(j) => { const w = document.querySelector('#learning__dropDownListW_' + j);"
                         " return w ? w.outerHTML : ''; }", jenis)
    path.write_text(html, encoding="utf-8")
    setup_logger().error("HTML daftar %s disimpan: %s", jenis, path)


def baca_daftar(page, jenis, timeout=TIMEOUT_MS):
    """Daftar lesson/step beserta status (done/inProgress/notStarted). Status tak dikenal = berhenti,
    kecuali step Test/Quiz/Exam: itu tidak dikerjakan bot apa pun statusnya, jadi tanpa penanda = "manual"."""
    try:  # daftar dirender belakangan (Angular): tunggu ada item dulu, jangan membaca daftar kosong
        page.locator(f"#learning__dropDownListW_{jenis} {SEL['item_daftar']}").first.wait_for(
            state="attached", timeout=timeout)
    except PWTimeout:
        pass  # kosong tetap ditolak di bawah, lengkap dengan screenshot
    hasil = page.evaluate(JS_DAFTAR, jenis)
    for h in hasil:
        if jenis == "steps" and h["status"] is None and STEP_MANUAL.search(h["nama"]):
            h["status"] = "manual"
    if not hasil or any(h["status"] is None for h in hasil):
        screenshot_on_fail(page, f"daftar_{jenis}_tak_terbaca")
        simpan_html_daftar(page, jenis)
        raise JenisSoalTidakDikenal(f"Daftar {jenis} kosong atau status progres tak terbaca.")
    return hasil


JS_DAFTAR_TERBUKA = """(jenis) => {
  const w = document.querySelector('#learning__dropDownListW_' + jenis);
  if (!w || !w.offsetParent && getComputedStyle(w).position !== 'fixed') return false;
  const r = w.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.top > -20 && r.bottom > 0 && r.right > 0
      && r.top < innerHeight && r.left < innerWidth;
}"""  # situs asli: terbuka top=62; tertutup top=-304 (tinggi 372, jadi bawahnya masih menyentuh layar)


def daftar_terbuka(page, jenis):
    """Daftar lesson/step benar-benar terlihat di layar. Daftar yang menutup dengan bergeser keluar
    layar (mis. sesudah Anda mengklik halaman) dianggap tertutup, walau elemennya masih ada."""
    return page.evaluate(JS_DAFTAR_TERBUKA, jenis)


def pilih_item(page, jenis, indeks, timeout=TIMEOUT_MS):
    """Buka dropdown lesson/step, klik item ke-`indeks`, tunggu item itu jadi yang aktif."""
    daftar = page.locator(f"#learning__dropDownListW_{jenis}")
    item = daftar.locator(SEL["item_daftar"]).nth(indeks)
    if not daftar_terbuka(page, jenis):
        click(page, page.locator(f"#learning__dropDownListTitleW_{jenis}"), f"buka_daftar_{jenis}", timeout)
        periksa(page, f"daftar_{jenis}_terbuka", lambda: page.wait_for_function(
            JS_DAFTAR_TERBUKA, arg=jenis, timeout=timeout))
    wait_visible(page, item, f"item_{jenis}_{indeks + 1}", timeout)
    sudah_aktif = "--current" in (item.get_attribute("class") or "")
    if not sudah_aktif:
        click(page, item.locator(".learning__dropDownList_itemName"), f"pilih_{jenis}_{indeks + 1}", timeout)
        periksa(page, f"{jenis}_{indeks + 1}_aktif", lambda: expect(item).to_have_class(
            re.compile(r"--current"), timeout=timeout))
    tunggu_stabil(page)  # beri waktu daftar menutup sendiri sebelum dicek
    if daftar_terbuka(page, jenis):  # masih terbuka (mis. item sudah aktif): tutup supaya tidak menutupi soal
        tutup_daftar(page, jenis, timeout)


OVERLAY_DAFTAR = ".utils__siteOverlay--LABody"  # situs asli: menutupi badan halaman selama daftar terbuka
JS_TITIK_OVERLAY = """(sel) => {
  const o = document.querySelector(sel); if (!o) return null;
  const r = o.getBoundingClientRect();
  for (const fy of [0.5, 0.6, 0.7, 0.4, 0.8, 0.3]) for (const fx of [0.02, 0.5, 0.98]) {
    const x = r.left + r.width * fx, y = r.top + r.height * fy;
    if (document.elementFromPoint(x, y) === o) return {x: x - r.left, y: y - r.top};
  }
  return null;
}"""  # titik di overlay badan yang tidak tertimpa daftar atau overlay lain (LABottomNav menumpuk tepi bawah)


def tutup_daftar(page, jenis, timeout=TIMEOUT_MS):
    """Tutup daftar lesson/step. Situs asli memasang overlay di atas halaman selama daftar terbuka, jadi
    judul daftar tak bisa diklik; klik titik overlay yang tidak tertimpa apa pun (terbukti menutup
    daftar di situs asli 2026-11-19). Tanpa overlay: klik judul. Tak ada titik bebas / masih terbuka = berhenti."""
    overlay = page.locator(OVERLAY_DAFTAR).first
    if overlay.count() and overlay.is_visible():
        titik = page.evaluate(JS_TITIK_OVERLAY, OVERLAY_DAFTAR)
        if titik is None:
            screenshot_on_fail(page, f"overlay_{jenis}_tertimpa")
            raise JenisSoalTidakDikenal("Overlay daftar tertimpa elemen lain; tidak ada titik aman untuk diklik.")
        click(page, overlay, f"tutup_daftar_{jenis}", timeout, position=titik)
    else:
        click(page, page.locator(f"#learning__dropDownListTitleW_{jenis}"), f"tutup_daftar_{jenis}", timeout)
    periksa(page, f"daftar_{jenis}_tertutup", lambda: page.wait_for_function(
        f"(j) => !({JS_DAFTAR_TERBUKA})(j)", arg=jenis, timeout=timeout))
    tunggu_stabil(page)


KUNCI_LESSON = "#learning__dropDownListTitleW_lessons.learning__dropDownListTitleW--disabled"


def lesson_terkunci(page):
    """Situs asli mengunci daftar lesson (judul berkelas --disabled) selama step aktif adalah Test."""
    return page.locator(KUNCI_LESSON).count() > 0


def buka_kunci_lesson(page, timeout=TIMEOUT_MS):
    """Kalau daftar lesson terkunci, pindah ke step non-Test pertama di lesson ini (hanya pindah
    tampilan: tidak menjawab, step Test tidak disentuh). False kalau tak bisa dibuka (gagal tertutup)."""
    log = setup_logger()
    if not lesson_terkunci(page):
        return True
    log.info("Daftar lesson terkunci (step Test aktif): pindah ke step non-Test untuk membukanya")
    for si, step in enumerate(baca_daftar(page, "steps", timeout)):  # batas atas = jumlah step
        if STEP_MANUAL.search(step["nama"]):
            continue
        pilih_item(page, "steps", si, timeout)
        try:
            page.wait_for_function(f"() => !document.querySelector({KUNCI_LESSON!r})",
                                   timeout=min(timeout, 6000))
            return True
        except PWTimeout:
            break
    log.warning("Daftar lesson tetap terkunci; unit ini dilewati.")
    screenshot_on_fail(page, "daftar_lesson_terkunci")
    return False


def cari_target(page, dilewati, timeout=TIMEOUT_MS):
    """Cari (lesson, indeks step, nama step) pertama yang belum selesai dan bukan step manual.
    Lesson yang hanya tersisa step manual dicatat di `dilewati` (per unit). Tidak ada = None."""
    for li, lesson in enumerate(baca_daftar(page, "lessons")):  # batas atas = jumlah lesson
        if lesson["status"] == "done" or lesson["nama"] in dilewati:
            continue
        if not buka_kunci_lesson(page, timeout):  # step Test aktif mengunci daftar lesson
            return None
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


SEL_AREA = "#learning__dropDownListTitleW_lessons"  # tanda area belajar sudah tampil


def buka_unit(page, unit_dicoba, timeout=TIMEOUT_MS):
    """Dari dashboard: klik unit pertama yang belum "Completed!" dan belum dicoba. Kembalikan nama
    unit (teks kartu), atau None kalau tak ada."""
    kartu = page.locator(SEL["kartu_unit"])
    wait_visible(page, kartu.first, "kartu_unit", timeout)
    for n in range(min(kartu.count(), MAX_UNIT)):  # batas atas = jumlah kartu
        if n in unit_dicoba or "Completed!" in kartu.nth(n).inner_text():
            continue
        unit_dicoba.add(n)
        nama = kartu.nth(n).inner_text().replace("\n", " ")[:50]
        setup_logger().info("Buka unit ke-%d: %s", n + 1, nama)
        click(page, kartu.nth(n), f"kartu_unit_{n + 1}", timeout)
        area = page.locator(SEL_AREA)
        salah_satu = page.locator(f"{SEL_AREA}:visible").or_(kartu.nth(n).locator(f"{SEL['daftar_lesson_kartu']}:visible"))
        wait_visible(page, salah_satu.first, "area_atau_daftar_lesson_kartu", max(timeout, TUNGGU_AREA_MS))
        if not area.is_visible():  # situs asli: kartu unit yang bukan unit aktif berbalik menampilkan daftar lesson
            lesson = kartu.nth(n).locator(SEL["lesson_kartu"])
            if lesson.count() == 0:  # semua lesson terkunci: gagal tertutup, unit dilewati
                setup_logger().warning("Unit ke-%d: semua lesson terkunci, dilewati.", n + 1)
                screenshot_on_fail(page, f"unit_{n + 1}_terkunci")
                continue
            # lesson pertama hanya pintu masuk area belajar; lesson target dipilih lewat dropdown
            click(page, lesson.first, f"lesson_pertama_unit_{n + 1}", timeout)
        wait_visible(page, area, "area_belajar", max(timeout, TUNGGU_AREA_MS))
        tunggu_stabil(page)
        return nama
    return None


def kembali_ke_dashboard(page, timeout=TIMEOUT_MS):
    tunggu = max(timeout, TUNGGU_DASHBOARD_MS)  # klik menunggu navigasi; situs asli kadang >10 detik
    click(page, page.locator(SEL["rumah"]), "ikon_rumah", tunggu)
    wait_visible(page, page.locator(SEL["kartu_unit"]).first, "dashboard", tunggu)


def catat_rencana(page, unit, lesson, rencana, timeout=TIMEOUT_MS):
    """Uji kering: catat step yang akan dikerjakan dan yang dilewati (Test) di lesson yang sedang dibuka."""
    steps = baca_daftar(page, "steps", timeout)
    akan = [s["nama"].strip() for s in steps if s["status"] != "done" and not STEP_MANUAL.search(s["nama"])]
    lewat = [s["nama"].strip() for s in steps if STEP_MANUAL.search(s["nama"])]
    if any(r["unit"] == "(area saat ini)" and (r["lesson"], r["dikerjakan"], r["dilewati"]) == (lesson, akan, lewat)
           for r in rencana):  # mulai dari area: unit yang sama dibuka lagi lewat kartu dashboard
        return
    rencana.append({"unit": unit, "lesson": lesson, "dikerjakan": akan, "dilewati": lewat})
    setup_logger().info("RENCANA | unit %s | lesson %s | dikerjakan: %s | dilewati (Test): %s",
                        unit, lesson, akan or "-", lewat or "-")


def jalankan_pelajaran(page, timeout=TIMEOUT_MS, maks_halaman=MAX_TOTAL_HALAMAN, hanya_baca=False):
    """Mulai dari dashboard (atau area belajar), kerjakan lesson demi lesson sampai semua unit
    selesai, kecuali step Test yang dikerjakan manual. Berhenti kalau ada jenis soal tak dikenal.
    hanya_baca=True (uji kering): hanya berpindah unit/lesson/step dan mencatat rencana, tidak menjawab."""
    log = setup_logger()
    ringkasan = {"halaman": 0, "tak_terverifikasi": 0}
    rencana, unit = [], "(area saat ini)"
    unit_dicoba, langkah = set(), 0
    if not ada_dashboard(page) and not ada_area(page):
        screenshot_on_fail(page, "bukan_dashboard_atau_area")
        raise JenisSoalTidakDikenal(f"Bukan dashboard atau area belajar: {page.url.split('?')[0]}")
    while True:
        if ada_dashboard(page):
            unit = buka_unit(page, unit_dicoba, timeout)
            if unit is None:
                log.info("Semua unit selesai (selain step Test).")
                break
        dilewati, dicoba = set(), set()  # nama lesson berulang antar unit, jadi dicatat per unit
        while True:
            langkah += 1
            if langkah > MAX_STEP or ringkasan["halaman"] >= maks_halaman:
                log.warning("Batas langkah/halaman tercapai, berhenti.")
                if not hanya_baca:
                    klik_header(page, timeout)
                break
            target = buka_lesson_berikutnya(page, dilewati, dicoba, timeout)
            if target is None:
                break
            if hanya_baca:
                catat_rencana(page, unit, target[0], rencana, timeout)
                dilewati.add(target[0])  # lanjut ke lesson berikutnya tanpa menjawab apa pun
                continue
            kerjakan_berurutan(page, ringkasan, maks_halaman - ringkasan["halaman"], timeout)
        if langkah > MAX_STEP or ringkasan["halaman"] >= maks_halaman:
            return ringkasan
        kembali_ke_dashboard(page, timeout)
    if hanya_baca:
        ringkasan["rencana"] = rencana
        log.info("Uji kering selesai: %d lesson punya step yang akan dikerjakan; tidak ada yang dijawab.", len(rencana))
        return ringkasan
    klik_header(page, timeout)  # terakhir, supaya modal dari menu Help tidak menghalangi soal
    log.info("Ringkasan: %s", ringkasan)
    return ringkasan

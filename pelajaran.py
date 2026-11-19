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
    "klas_zona": ".prCl__container--normal .dndZone",  # soal klasifikasi (tabel True/False, kolom orang): satu kolom banyak item
    "klas_kata": ".prCl__container--bank .dnditem",
    "gambar_kotak": ".prTextToPic__container--reg .dndZone",  # pasangkan kata ke gambar: satu kata per gambar
    "gambar_kata": ".prTextToPic__wordsBankWrapper .dnditem",
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
# (textarea dikte prOpenEnded sudah punya handler: isi_teks_bebas)
JS_ISIAN_TEKS = """() => [...document.querySelectorAll('textarea, [contenteditable=true], input[type=text]')]
    .some(e => !e.closest('#DictionaryPanelContainer') && !e.matches('.prOpenEnded__qaItemText--textarea')
               && e.offsetParent !== null)"""
TEKS_BEBAS = ".prOpenEnded__qaItemText--textarea"  # soal dikte/isian bebas: satu textarea per kalimat
ISIAN_TEKS = "a"  # jawaban salah tidak masalah (keputusan pemilik akun); yang perlu: soal tercatat dikerjakan
MAX_TEKS_BEBAS = 20  # batas textarea per halaman; lebih dari ini = bentuk halaman tak terduga, berhenti
# Soal menulis (prWriting): editor TinyMCE di iframe, tombol Done; kurang dari 5 kata ditolak situs.
TULISAN = {
    "area": ".prWriting__practice",
    "editor": ".prWriting__editorW iframe[id$=_ifr]",  # iframe TinyMCE; isinya body#tinymce
    "kata": ".prWriting__editorWords",
    "done": ".prWriting__action--submit",
    "done_nonaktif": ".prWriting__action--submit.prWriting__action--disabled",
}
TEKS_TULISAN = "The waiter says that the two women ordered food and drinks at the restaurant."  # tak dinilai (keputusan pemilik akun)
MIN_KATA_TULISAN = 5
MAX_KLASIFIKASI = 30  # batas item klasifikasi yang ditempatkan per halaman
MEDIA_JALAN = ("() => [...document.querySelectorAll('video,audio')]"
               ".some(m => !m.paused && m.currentTime > 0)")
MEDIA_SELESAI = ("() => [...document.querySelectorAll('video,audio')]"
                 ".some(m => m.ended || (m.duration > 0 && m.currentTime >= m.duration - 0.5))")
JS_PASANG_AKHIR = """() => { window.__botSelesai = false;
  document.querySelectorAll('video,audio').forEach((m) => {
    m.addEventListener('ended', () => { window.__botSelesai = true; });  // pemutar audio situs asli mengembalikan dirinya ke 0 saat selesai
    m.addEventListener('timeupdate', () => { if (m.duration > 0 && m.currentTime >= m.duration - 0.5) window.__botSelesai = true; });
  }); }"""  # state elemen saja tak cukup: keadaan "selesai" bisa hanya sekejap
MEDIA_DURASI = ("() => { const m = [...document.querySelectorAll('video,audio')]"
                ".find(m => !m.paused && m.currentTime > 0); return m ? m.duration : NaN; }")
MAX_DURASI_MEDIA = 20 * 60  # detik; durasi tak terbaca atau lebih panjang dari ini = tak ditunggu, berhenti
TAMBAHAN_TUNGGU_MEDIA = 30  # detik di atas durasi media
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


JS_DI_LAYAR = """(e) => { const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight; }"""


def di_layar(locator):
    """Elemen ada di dalam layar. Situs asli menyisakan tombol putar di luar layar pada halaman tanpa video
    (Playwright tetap menganggapnya terlihat, lalu kliknya timeout)."""
    return locator.evaluate(JS_DI_LAYAR)


def putar_video(page, timeout=TIMEOUT_MS):
    overlay = page.locator(SEL["video_overlay"])
    kustom = page.locator(SEL["video_kustom"])
    video = page.locator(SEL["video"]).first
    if video.count() and not overlay.count():  # situs asli: tombol putar muncul sesaat setelah halaman
        try:                                    # tampil; kalau video diklik dulu, tombol itu menghalanginya
            overlay.first.wait_for(state="visible", timeout=min(timeout, 3000))
        except PWTimeout:
            pass
    if overlay.count() and overlay.first.is_visible() and di_layar(overlay.first):
        click(page, overlay.first, "video_tombol_putar", timeout)
    elif kustom.count() and kustom.is_visible() and di_layar(kustom):
        click(page, kustom, "video_tombol_putar", timeout)
    elif video.count() and video.is_visible() and di_layar(video):
        if video.evaluate("v => v.paused"):  # jangan klik kalau sudah berjalan (bisa menjeda)
            click(page, video, "video", timeout)
    else:
        return False
    periksa(page, "video_terputar", lambda: page.wait_for_function(MEDIA_JALAN, timeout=timeout))
    durasi = page.evaluate(MEDIA_DURASI)  # situs menghitung progres hanya kalau media diputar sampai habis
    if not isinstance(durasi, (int, float)) or not 0 < durasi <= MAX_DURASI_MEDIA:
        screenshot_on_fail(page, "durasi_media_tak_wajar")
        raise JenisSoalTidakDikenal(f"Durasi media tak terbaca atau di luar batas: {durasi!r}")
    setup_logger().info("Menunggu media selesai (%.0f detik)", durasi)
    page.evaluate(JS_PASANG_AKHIR)
    periksa(page, "video_selesai", lambda: page.wait_for_function(
        f"() => window.__botSelesai === true || ({MEDIA_SELESAI})()", timeout=int((durasi + TAMBAHAN_TUNGGU_MEDIA) * 1000)))
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
        semua = himpunan.nth(n).locator(SEL["radio"])
        pertama = label = None
        for k in range(semua.count()):  # batas atas = jumlah radio di pertanyaan ini
            radio = semua.nth(k)
            id_ = radio.get_attribute("id", timeout=timeout)
            if not id_:
                screenshot_on_fail(page, f"radio_tanpa_id_{n + 1}")
                raise JenisSoalTidakDikenal(f"Radio pertanyaan {n + 1} tanpa id; label tak bisa dicari.")
            kandidat = himpunan.nth(n).locator(f'label[for="{id_}"]')
            if kandidat.count() and kandidat.first.is_visible():  # situs menyimpan opsi "None" tersembunyi di urutan pertama
                pertama, label = radio, kandidat
                break
        if pertama is None:
            screenshot_on_fail(page, f"radio_tak_terlihat_{n + 1}")
            raise JenisSoalTidakDikenal(f"Pertanyaan {n + 1} tak punya opsi yang terlihat.")
        click(page, label, f"pertanyaan_{n + 1}_pilihan_1", timeout)
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


def isi_klasifikasi(page, timeout=TIMEOUT_MS):
    """Soal klasifikasi (prCl): bagikan item di bank ke kolom secara bergiliran (jawaban salah tidak masalah,
    yang perlu: semua item ditempatkan dan soal dicek). Batas atas MAX_KLASIFIKASI item; bank tak habis = berhenti."""
    zona = page.locator(SEL["klas_zona"])
    n_zona = zona.count()
    if not n_zona:
        return False
    for k in range(MAX_KLASIFIKASI):
        bank = page.locator(SEL["klas_kata"])
        sisa = bank.count()
        if not sisa:
            return True
        seret(page, bank.first, zona.nth(k % n_zona), f"klasifikasi_item_{k + 1}_ke_kolom_{k % n_zona + 1}", timeout)
        periksa(page, f"klasifikasi_item_{k + 1}_ditempatkan", lambda s=sisa: expect(
            page.locator(SEL["klas_kata"])).to_have_count(s - 1, timeout=timeout))
    screenshot_on_fail(page, "klasifikasi_bank_tak_habis")
    raise JenisSoalTidakDikenal(f"Bank klasifikasi masih berisi item setelah {MAX_KLASIFIKASI} percobaan.")


JS_DND_ASING = """(sel) => [...document.querySelectorAll('.dndZone')].filter((z) => z.getBoundingClientRect().width > 0)
  .filter((z) => !z.closest('.bankContainer, .dndBank, [class*="ordsBank"]'))
  .filter((z) => !sel.some((s) => z.matches(s))).length"""  # zona seret di luar bank yang tak dicakup handler mana pun


def elemen_belum_didukung(page):
    """Nama elemen soal tanpa handler (suara, isian teks, zona seret asing) kalau ada di halaman; kalau tidak, None."""
    if page.locator(SEL["webrtc"]).count():
        return "suara (webRtc)"
    asing = page.evaluate(JS_DND_ASING, [SEL["cloze_kotak"], SEL["cocok_kotak"], SEL["klas_zona"], SEL["gambar_kotak"]])
    if asing:
        return f"zona seret tanpa handler ({asing})"
    if page.evaluate(JS_ISIAN_TEKS):
        return "isian teks"
    return None


JS_HALAMAN_BACAAN = """(sel) => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const q = (x) => [...document.querySelectorAll(x)].filter(vis);
  const kontrol = q('input, select, textarea, [contenteditable], .dndZone, .dnditem, button')
    .filter((e) => !e.closest('#DictionaryPanelContainer, [id^="sitemenu__"]'));  // sitemenu: tombol menu header situs asli
  return q(sel.cek).length === 0 && q(sel.next).length > 0 && kontrol.length === 0;
}"""


def halaman_bacaan(page):
    """True kalau halaman hanya bacaan: Next terlihat, tetapi tidak ada Check Answer maupun kontrol isian
    yang terlihat. Cukup Next sekali; situs mencatatnya sebagai dikerjakan. Ragu = False (bot berhenti)."""
    return page.evaluate(JS_HALAMAN_BACAAN, {"cek": SEL["cek"], "next": SEL["next"]})


def isi_teks_bebas(page, timeout=TIMEOUT_MS):
    """Soal dikte/isian bebas (prOpenEnded): isi tiap textarea yang terlihat dengan teks apa saja. Cara ini
    dipelajari dari rekaman pengguna (ketik di textarea lalu Check Answer)."""
    kotak = page.locator(f"{TEKS_BEBAS}:visible")
    n = kotak.count()
    if n == 0:
        return False
    if n > MAX_TEKS_BEBAS:
        screenshot_on_fail(page, "teks_bebas_terlalu_banyak")
        raise JenisSoalTidakDikenal(f"{n} kotak teks (batas {MAX_TEKS_BEBAS}).")
    for i in range(n):
        setup_logger().info("Isi teks: kotak_%d", i + 1)
        kotak.nth(i).fill(ISIAN_TEKS, timeout=timeout)
        kotak.nth(i).blur()  # memicu 'change' seperti pengguna yang berpindah kotak
        periksa(page, f"teks_{i + 1}_terisi", lambda k=kotak.nth(i): expect(k).to_have_value(ISIAN_TEKS, timeout=timeout))
    return True


def isi_tulisan(page, timeout=TIMEOUT_MS):
    """Soal menulis (prWriting): ketik kalimat Inggris di editor TinyMCE, tunggu penghitung kata cukup, klik Done.
    Berhasil kalau editor terkunci (contenteditable=false), seperti pada rekaman pengguna. Modal peringatan
    ("Oops...") atau editor tak terkunci = berhenti; modalnya tidak ditutup diam-diam."""
    log = setup_logger()
    if not page.locator(TULISAN["area"]).count():
        return False
    editor = page.frame_locator(TULISAN["editor"]).locator("body#tinymce")
    if editor.get_attribute("contenteditable", timeout=timeout) == "false":
        log.info("Soal menulis sudah terkunci (sudah dikerjakan)")
        return True
    log.info("Isi tulisan: %d kata", len(TEKS_TULISAN.split()))
    editor.click(timeout=timeout)
    page.keyboard.type(TEKS_TULISAN)
    periksa(page, "tulisan_kata_cukup", lambda: page.wait_for_function(
        "([s, n]) => parseInt(document.querySelector(s).textContent, 10) >= n",
        arg=[TULISAN["kata"], MIN_KATA_TULISAN], timeout=timeout))
    periksa(page, "tulisan_done_aktif", lambda: expect(page.locator(TULISAN["done_nonaktif"])).to_have_count(0, timeout=timeout))
    click(page, page.locator(TULISAN["done"]), "tulisan_done", timeout)
    try:
        expect(editor).to_have_attribute("contenteditable", "false", timeout=min(timeout, 8000))
    except AssertionError:
        screenshot_on_fail(page, "tulisan_tak_diterima")
        raise JenisSoalTidakDikenal("Done tidak diterima situs (ada peringatan validasi atau editor tak terkunci).")
    log.info("OK: tulisan_terkunci")
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
    if (TIDAK_DIDUKUNG.match(teks) and not page.locator(f"{TEKS_BEBAS}:visible").count()
            and not page.locator(TULISAN["area"]).count()):  # instruksi (mis. "Type ...") yang belum bisa dikerjakan bot
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
    if isi_teks_bebas(page, timeout):
        dikerjakan.append("isian teks")
        perlu_cek = True
    if isi_tulisan(page, timeout):
        dikerjakan.append("tulisan")  # Done tidak butuh Check Answer
    if isi_seret(page, SEL["cloze_kotak"], SEL["cloze_kata"], "cloze", timeout):
        dikerjakan.append("isian kata")
        perlu_cek = True
    if isi_seret(page, SEL["cocok_kotak"], SEL["cocok_kata"], "pencocokan", timeout):
        dikerjakan.append("pencocokan")
        perlu_cek = True
    if isi_seret(page, SEL["gambar_kotak"], SEL["gambar_kata"], "gambar", timeout):
        dikerjakan.append("kata ke gambar")
        perlu_cek = True
    if isi_klasifikasi(page, timeout):
        dikerjakan.append("klasifikasi")
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


REMINDER = re.compile(r"You need to complete the activit(?:y|ies) (\d+(?:\s*(?:,|and)\s*\d+)*)")  # "activity 2", "activities 3, 4 and 7"
REMINDER_MEDIA = re.compile(r"You need to play the video/audio")
JUDUL_REMINDER = re.compile(r"^\s*Reminder!\s*$")
SEL_PAGER = ".learning__tasksNav_tasksW .learning__tasksNav_task"  # nomor halaman di bawah
MAX_PERCOBAAN_REMINDER = 5  # batas siklus "tetap di step" per jendela Reminder


def cari_teks(page, pola, exact=False):
    """Elemen pertama yang terlihat dengan teks `pola` di frame mana pun (jendela Reminder bisa di iframe)."""
    for frame in page.frames:
        teks = frame.get_by_text(pola, exact=exact)
        if teks.count() > 0 and teks.first.is_visible():
            return teks.first
    return None


def reminder_terlihat(page):
    return any(cari_teks(page, p) for p in (REMINDER, REMINDER_MEDIA, JUDUL_REMINDER))


JS_OVERLAY = """() => { const e = document.elementFromPoint(innerWidth / 2, innerHeight * 0.8);
  return !!e && !!e.closest('#EdoFrameBox'); }"""  # #EdoFrameBox: lapisan yang menutupi halaman selama jendela terbuka
TUNGGU_REMINDER_DETIK = 15  # batas tunggu teks Reminder muncul sesudah lapisan menutupi halaman
JEDA_POLL_MS = 300


def overlay_menutupi(page):
    return page.evaluate(JS_OVERLAY)


def tunggu_reminder(page):
    """Lapisan #EdoFrameBox menutupi halaman tapi teks Reminder belum terbaca (situs asli 11:36: kartu sempat
    kosong). Tunggu teksnya muncul (polling terbatas). True kalau Reminder terbaca; False kalau tidak ada lapisan
    atau teks tak kunjung muncul (lapisan tak dikenal: isi tiap frame dicatat sebagai bukti)."""
    log = setup_logger()
    if not overlay_menutupi(page):
        return reminder_terlihat(page)
    for _ in range(int(TUNGGU_REMINDER_DETIK * 1000 / JEDA_POLL_MS)):  # batas atas
        if reminder_terlihat(page):
            return True
        page.wait_for_timeout(JEDA_POLL_MS)
    log.error("Lapisan #EdoFrameBox menutupi halaman, teks Reminder tak muncul dalam %d dtk.", TUNGGU_REMINDER_DETIK)
    for i, frame in enumerate(page.frames):
        try:
            isi = frame.evaluate("() => document.body ? document.body.innerHTML.slice(0, 400) : ''")
        except Exception as err:  # frame sedang berpindah
            isi = f"(tak terbaca: {err})"
        log.error("frame %d %s: %s", i, frame.url[:80], isi.replace("\n", " "))
    return False


def ke_halaman(page, nomor, timeout=TIMEOUT_MS):
    """Pindah ke halaman soal bernomor `nomor` (mulai 1) lewat pager bawah."""
    item = page.locator(SEL_PAGER).nth(nomor - 1)
    click(page, item, f"pager_{nomor}", timeout)
    periksa(page, f"pager_{nomor}_aktif", lambda: expect(item).to_have_class(re.compile(r"--current"), timeout=timeout))
    tunggu_stabil(page)


def selesaikan_reminder(page, ringkasan, timeout=TIMEOUT_MS):
    """Jendela "You need to complete the activity N": tetap di step, kerjakan halaman N, kembali ke halaman
    terakhir, Next lagi. N sudah pernah dicoba, halaman N tak bisa dikerjakan, atau batas siklus = klik
    Continue (lewati). Kembalikan "lanjut" (jendela hilang) atau "lewat" (step dilewati)."""
    log = setup_logger()
    dicoba = set()
    for _ in range(MAX_PERCOBAAN_REMINDER):
        if not tunggu_reminder(page):  # kartu Reminder (iframe MsgPage.html) memuat belakangan; jangan simpulkan "hilang" terlalu cepat
            return "lanjut"
        if cari_teks(page, REMINDER_MEDIA):  # video/audio belum diputar sampai habis: tetap, putar, Next lagi
            log.info("Reminder: video/audio belum diputar; tetap di step dan memutarnya.")
            click(page, cari_teks(page, "Stay in this step", exact=True), "reminder_tetap_di_step", timeout)
            try:
                putar_video(page, timeout)
            except JenisSoalTidakDikenal as err:
                log.warning("Media tak bisa diputar bot (%s); step akan dilewati.", err)
                break
            lanjut(page, timeout)
            continue
        ada = cari_teks(page, REMINDER)
        if ada is None:  # jendela Reminder bertulisan lain: jangan menebak dan jangan klik Continue
            screenshot_on_fail(page, "reminder_tak_dikenal")
            raise JenisSoalTidakDikenal("Jendela Reminder dengan teks yang tak dikenal bot.")
        jumlah = page.locator(SEL_PAGER).count()
        daftar = [int(x) for x in re.findall(r"\d+", REMINDER.search(ada.inner_text()).group(1))]
        nomor = next((n for n in daftar if n not in dicoba and 1 <= n <= jumlah), None)  # satu aktivitas per siklus
        if nomor is None:
            break
        dicoba.add(nomor)
        log.info("Reminder: aktivitas %d belum selesai; tetap di step dan mengerjakannya.", nomor)
        click(page, cari_teks(page, "Stay in this step", exact=True), "reminder_tetap_di_step", timeout)
        ke_halaman(page, nomor, timeout)
        try:
            kerjakan_halaman(page, ringkasan, timeout)
        except JenisSoalTidakDikenal as err:
            log.warning("Aktivitas %d tak bisa dikerjakan bot (%s); akan dilewati.", nomor, err)
        ke_halaman(page, jumlah, timeout)
        lanjut(page, timeout)
    if reminder_terlihat(page):
        log.warning("Reminder tak terselesaikan; klik Continue (step dilewati).")
        screenshot_on_fail(page, "reminder_dilewati")
        click(page, cari_teks(page, "Continue", exact=True), "reminder_continue", timeout)
        tunggu_stabil(page)
        return "lewat"
    return "lanjut"


def kerjakan_berurutan(page, ringkasan, maks, timeout=TIMEOUT_MS, tanya=None):
    """Kerjakan halaman satu per satu lalu Next. Kembalikan alasan berhenti:
    "habis" (Next tidak mengubah halaman), "test" (step Test, dikerjakan manual), "lewat" (step dilewati
    lewat Continue di jendela Reminder), "batas".
    tanya (opsional): dipanggil tanya(page, alasan) kalau bot tak tahu cara mengerjakan halaman; harus menunggu
    pengguna selesai mengerjakannya sendiri (sambil merekam), lalu bot lanjut Next. Tanpa tanya: bot berhenti (gagal tertutup)."""
    log = setup_logger()
    mulai = ringkasan["halaman"]
    while ringkasan["halaman"] - mulai < maks:
        ringkasan["halaman"] += 1
        log.info("== Halaman %d", ringkasan["halaman"])
        tunggu_stabil(page)
        if tunggu_reminder(page):  # Reminder sudah terbuka sejak awal
            if selesaikan_reminder(page, ringkasan, timeout) == "lewat":
                return "lewat"
        elif overlay_menutupi(page):
            screenshot_on_fail(page, "overlay_tak_dikenal")
            raise JenisSoalTidakDikenal("Lapisan menutupi halaman tapi bukan Reminder yang dikenal bot.")
        if sedang_test(page):
            ringkasan["halaman"] -= 1
            log.info("Step Test (dikerjakan manual): berhenti di sini, tidak disentuh.")
            return "test"
        if page.locator(SEL["intro"]).count():
            log.info("Layar intro step: langsung Next")
        else:
            try:
                kerjakan_halaman(page, ringkasan, timeout)
            except JenisSoalTidakDikenal as err:
                if tanya is None:
                    raise
                ringkasan["manual"] = ringkasan.get("manual", 0) + 1
                log.warning("Bot tak tahu cara halaman ini (%s); menunggu pengguna mengerjakannya.", err)
                tanya(page, str(err))
        berganti = lanjut(page, timeout)
        if not berganti and not tunggu_reminder(page) and overlay_menutupi(page):
            screenshot_on_fail(page, "overlay_tak_dikenal")
            raise JenisSoalTidakDikenal("Lapisan menutupi halaman tapi bukan Reminder yang dikenal bot.")
        if reminder_terlihat(page):  # Reminder membuat Next tampak "tak berubah"; periksa sebelum menyimpulkan habis
            if selesaikan_reminder(page, ringkasan, timeout) == "lewat":
                return "lewat"
            continue
        if not berganti:
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
            re.compile(r"--current"), timeout=max(timeout, TUNGGU_AREA_MS)))  # pindah lesson di situs asli bisa >10 dtk
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


def cari_target(page, dilewati, timeout=TIMEOUT_MS, lewat_step=frozenset()):
    """Cari (lesson, indeks step, nama step) pertama yang belum selesai dan bukan step manual.
    Lesson yang hanya tersisa step manual dicatat di `dilewati` (per unit). Tidak ada = None."""
    for li, lesson in enumerate(baca_daftar(page, "lessons")):  # batas atas = jumlah lesson
        if lesson["status"] == "done" or lesson["nama"] in dilewati:
            continue
        if not buka_kunci_lesson(page, timeout):  # step Test aktif mengunci daftar lesson
            return None
        pilih_item(page, "lessons", li, timeout)
        for si, step in enumerate(baca_daftar(page, "steps")):  # batas atas = jumlah step
            if (step["status"] != "done" and not STEP_MANUAL.search(step["nama"])
                    and (lesson["nama"], step["nama"]) not in lewat_step):  # lewat_step: dilewati via Reminder
                return lesson["nama"], si, step["nama"]
        dilewati.add(lesson["nama"])
    return None


TUNGGU_STATUS_DETIK = 60  # batas tunggu status step diperbarui situs sesudah dikerjakan
JEDA_STATUS_MS = 3000


def tunggu_step_selesai(page, indeks, detik=TUNGGU_STATUS_DETIK):
    """Tunggu status step ke-`indeks` (di lesson yang sedang dipilih) jadi "done" (polling terbatas, baca saja).
    Bukti situs asli: status Practice masih "inProgress" 3 detik sesudah selesai, lalu "done" ±40 detik kemudian."""
    for _ in range(max(1, int(detik * 1000 / JEDA_STATUS_MS))):  # batas atas
        daftar = page.evaluate(JS_DAFTAR, "steps")
        if indeks < len(daftar) and daftar[indeks]["status"] == "done":
            return True
        page.wait_for_timeout(JEDA_STATUS_MS)
    return False


def gagal_tanpa_kemajuan(page, target):
    screenshot_on_fail(page, "tidak_ada_kemajuan")
    status = [(s["nama"], s["status"]) for s in page.evaluate(JS_DAFTAR, "steps")]  # bukti untuk diagnosa
    raise RuntimeError(f"Tidak ada kemajuan: {target} dipilih lagi padahal sudah dikerjakan. Status step: {status}")


def buka_lesson_berikutnya(page, dilewati, dicoba, timeout=TIMEOUT_MS, lewat_step=frozenset()):
    """Dari area belajar: pilih lesson pertama yang belum selesai, lalu step pertama yang belum selesai
    (bukan Test), dan tunggu halaman pertamanya siap. None kalau unit ini habis."""
    log = setup_logger()
    target = cari_target(page, dilewati, timeout, lewat_step)
    if target is None:
        return None
    if target in dicoba:  # sudah dikerjakan tapi statusnya belum selesai: situs bisa terlambat memperbarui (±40 dtk)
        if not tunggu_step_selesai(page, target[1]):
            gagal_tanpa_kemajuan(page, target)
        target = cari_target(page, dilewati, timeout, lewat_step)
        if target is None:
            return None
        if target in dicoba:
            gagal_tanpa_kemajuan(page, target)
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


def jalankan_pelajaran(page, timeout=TIMEOUT_MS, maks_halaman=MAX_TOTAL_HALAMAN, hanya_baca=False, tanya=None):
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
        dilewati, dicoba, lewat_step = set(), set(), set()  # nama lesson berulang antar unit, jadi dicatat per unit
        while True:
            langkah += 1
            if langkah > MAX_STEP or ringkasan["halaman"] >= maks_halaman:
                log.warning("Batas langkah/halaman tercapai, berhenti.")
                if not hanya_baca:
                    klik_header(page, timeout)
                break
            target = buka_lesson_berikutnya(page, dilewati, dicoba, timeout, lewat_step)
            if target is None:
                break
            if hanya_baca:
                catat_rencana(page, unit, target[0], rencana, timeout)
                dilewati.add(target[0])  # lanjut ke lesson berikutnya tanpa menjawab apa pun
                continue
            if kerjakan_berurutan(page, ringkasan, maks_halaman - ringkasan["halaman"], timeout, tanya) == "lewat":
                lewat_step.add((target[0], target[2]))
                ringkasan["step_dilewati"] = ringkasan.get("step_dilewati", 0) + 1
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

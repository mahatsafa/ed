"""Ambil struktur halaman dari tab yang sudah Anda buka. HANYA MEMBACA, tidak mengklik.

Sekali ambil : python ambil_html.py --target real --attach http://127.0.0.1:9222 --nama soal_video
Mode pantau  : python ambil_html.py --target real --attach http://127.0.0.1:9222 --nama les --pantau
  (pindah soal manual di Chrome; setiap soal baru disimpan otomatis; Ctrl+C untuk berhenti)
Hasil di logs/ : <nama>_frame<N>.html (tanpa script/style), <nama>_elemen.json, <nama>.png
  (mode pantau: <nama>01_..., <nama>02_..., dst.)
"""
import argparse
import hashlib
import json
import re
import sys

from playwright.sync_api import sync_playwright

from bot import CIRI_HALAMAN, cari_tab
from helpers import LOG_DIR, setup_logger

MAX_ELEMEN = 400  # batas elemen per frame
MAX_TEKS = 80  # batas panjang teks per elemen
MAX_FRAME = 20  # batas jumlah frame yang disimpan
MAX_SNAPSHOT = 40  # batas jumlah hasil di mode pantau, lalu berhenti sendiri
JEDA_PANTAU_MS = 2000  # jeda antar pengecekan di mode pantau
PEMILIH = ("video, audio, input, textarea, select, button, a[href], [role=button], "
           "[contenteditable=true], [onclick], [ng-click], [data-ng-click]")

JS_ELEMEN = """([pemilih, maxEl, maxTeks]) => {
  const hasil = [];
  for (const el of document.querySelectorAll(pemilih)) {
    if (hasil.length >= maxEl) break;
    const r = el.getBoundingClientRect();
    const type = el.getAttribute('type');
    const aman = ['radio', 'checkbox', 'button', 'submit'].includes(type);  // value isian tidak diambil
    hasil.push({
      tag: el.tagName.toLowerCase(), id: el.id || null,
      class: typeof el.className === 'string' ? el.className : null,
      name: el.getAttribute('name'), type: type,
      value: aman ? el.getAttribute('value') : null,
      placeholder: el.getAttribute('placeholder'),
      aria: el.getAttribute('aria-label'), title: el.getAttribute('title'),
      teks: (el.innerText || '').trim().slice(0, maxTeks),
      terlihat: r.width > 0 && r.height > 0,
      nonaktif: el.disabled === true,
    });
  }
  return hasil;
}"""


def bersihkan(html):
    """Buang script, style, dan data URI besar supaya file kecil dan mudah dibaca."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    return re.sub(r"data:[^\"')\s]{100,}", "data:...", html)


def nama_valid(nama):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", nama):
        raise SystemExit("--nama hanya boleh huruf/angka/_/- (maks 40 karakter).")
    return nama


def simpan(page, nama, log):
    """Simpan HTML tiap frame, daftar elemen, dan screenshot dengan awalan nama."""
    semua = []
    for i, frame in enumerate(page.frames[:MAX_FRAME]):
        try:
            html = bersihkan(frame.content())
            elemen = frame.evaluate(JS_ELEMEN, [PEMILIH, MAX_ELEMEN, MAX_TEKS])
        except Exception as err:  # satu frame gagal tidak menghentikan yang lain
            log.error("Frame %d dilewati: %s", i, err)
            continue
        (LOG_DIR / f"{nama}_frame{i}.html").write_text(html, encoding="utf-8")
        semua.append({"frame": i, "url": frame.url.split("?")[0], "elemen": elemen})
        log.info("%s frame %d: %d elemen, %d karakter HTML", nama, i, len(elemen), len(html))
    (LOG_DIR / f"{nama}_elemen.json").write_text(
        json.dumps(semua, indent=1, ensure_ascii=False), encoding="utf-8")
    page.screenshot(path=str(LOG_DIR / f"{nama}.png"))


def tanda(page):
    """Sidik jari halaman: URL dan teks tiap frame, angka dibuang (waktu video terus berubah)."""
    bagian = []
    for frame in page.frames[:MAX_FRAME]:
        try:
            teks = frame.evaluate("() => document.body ? document.body.innerText.slice(0, 3000) : ''")
        except Exception:
            teks = ""
        bagian.append(frame.url.split("?")[0] + "|" + re.sub(r"\d", "", teks))
    return hashlib.sha1("\n".join(bagian).encode("utf-8")).hexdigest()


def pantau(browser, target, nama, log):
    """Simpan halaman setiap kali isinya berganti dan sudah stabil dua pengecekan berturut-turut."""
    log.info("Mode pantau aktif (maks %d hasil). Pindah soal manual; Ctrl+C untuk berhenti.",
             MAX_SNAPSHOT)
    tersimpan = terakhir = None
    jumlah = 0
    try:
        while jumlah < MAX_SNAPSHOT:
            page = cari_tab(browser, target)
            sekarang = tanda(page)
            if sekarang == terakhir and sekarang != tersimpan:
                jumlah += 1
                simpan(page, f"{nama}{jumlah:02d}", log)
                tersimpan = sekarang
            terakhir = sekarang
            page.wait_for_timeout(JEDA_PANTAU_MS)
    except KeyboardInterrupt:
        pass
    log.info("Pantau selesai: %d hasil tersimpan.", jumlah)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["mock", "real"], default="real")
    parser.add_argument("--attach", required=True, metavar="URL_CDP")
    parser.add_argument("--nama", required=True, help="awalan nama file hasil")
    parser.add_argument("--pantau", action="store_true", help="simpan otomatis tiap soal berganti")
    args = parser.parse_args()
    nama = nama_valid(args.nama)

    log = setup_logger()
    LOG_DIR.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.attach)
        if args.pantau:
            pantau(browser, args.target, nama, log)
        else:
            page = cari_tab(browser, args.target)
            log.info("Ambil halaman (baca saja): %s", CIRI_HALAMAN[args.target])
            simpan(page, nama, log)
    log.info("Selesai. Hasil di %s", LOG_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        setup_logger().error("ambil_html berhenti: %s", err)
        sys.exit(1)

"""Rekam struktur tab yang sudah Anda buka, per state, per frame. HANYA MEMBACA, tidak mengklik.

Jalankan : python diagnosa.py --attach http://127.0.0.1:9222
  Bot meminta Anda pindah manual ke tiap state (dashboard, daftar_lesson, soal_1), lalu Enter.
  Tambah state lain dengan --state nama (boleh diulang; menggantikan daftar bawaan).
Hasil di logs/diagnosa_<waktu>/<state>/ : ringkasan.json, frame<N>.html (tanpa script/style),
  frame<N>.png (screenshot frame yang terlihat).
"""
import argparse
import json
import re
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

from ambil_html import MAX_FRAME, bersihkan
from bot import cari_tab
from helpers import LOG_DIR, setup_logger

STATE_BAWAAN = ("dashboard", "daftar_lesson", "soal_1")
MAX_STATE = 10  # batas jumlah state per jalan
MAX_KELAS = 200  # batas daftar nama kelas unik per frame
MAX_TOMBOL = 40  # batas tombol Next/Back yang dicatat per frame
SELEKTOR_KUNCI = (
    "[class*=learning__]", ".learning__headerIW", "#CheckAnswer", "a.tasksBtnext",
    ".learning__tasksNav_task--done", "input[type=radio]", "input.layout__radio", "select",
    "[class*=prCLZ__]", ".dndZone", ".dnditem", "video", "audio", "textarea",
    "[contenteditable]", "iframe", ".speakingInteractButtonWrapper",
    "[class*=home__unitIW]", "[class*=lesson]", "[class*=--done]", "[class*=complete]",
)
PREFIX_KELAS = ("learning__", "home__", "unit", "lesson")

JS_FRAME = """([kunci, prefix, maxKelas, maxTombol]) => {
  const hitung = {};
  for (const s of kunci) {
    try { hitung[s] = document.querySelectorAll(s).length; } catch (e) { hitung[s] = null; }
  }
  const kelas = new Set();
  for (const el of document.querySelectorAll('[class]')) {
    if (typeof el.className !== 'string') continue;
    for (const k of el.className.split(/\\s+/)) {
      if (kelas.size >= maxKelas) break;
      if (prefix.some(p => k.startsWith(p))) kelas.add(k);
    }
  }
  const tombol = [];
  for (const el of document.querySelectorAll('a, button, [role=button]')) {
    if (tombol.length >= maxTombol) break;
    const teks = (el.innerText || el.getAttribute('title') || el.getAttribute('aria-label') || '').trim();
    if (!/^(Next|Back|Previous)$/i.test(teks)) continue;
    const r = el.getBoundingClientRect();
    tombol.push({tag: el.tagName.toLowerCase(), id: el.id || null,
                 class: typeof el.className === 'string' ? el.className : null, teks: teks,
                 terlihat: r.width > 0 && r.height > 0});
  }
  return {judul: document.title, jumlah_elemen: document.querySelectorAll('*').length,
          selektor: hitung, tombol_nav: tombol, kelas_unik: [...kelas].sort()};
}"""


def nama_state_valid(nama):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", nama):
        raise SystemExit("Nama state hanya boleh huruf/angka/_/- (maks 40 karakter).")
    return nama


def info_frame(page, i, frame, folder, log):
    """Rekam satu frame. Gagal -> dicatat sebagai galat, frame lain tetap jalan."""
    info = {"frame": i, "nama": frame.name, "url": frame.url.split("?")[0],
            "induk": page.frames.index(frame.parent_frame) if frame.parent_frame else None}
    try:
        info.update(frame.evaluate(JS_FRAME, [list(SELEKTOR_KUNCI), list(PREFIX_KELAS),
                                              MAX_KELAS, MAX_TOMBOL]))
        (folder / f"frame{i}.html").write_text(bersihkan(frame.content()), encoding="utf-8")
    except Exception as err:
        info["galat"] = str(err)[:200]
        log.error("Frame %d dilewati: %s", i, err)
        return info
    if frame == page.main_frame:
        page.screenshot(path=str(folder / f"frame{i}.png"), full_page=True)
        return info
    try:
        kotak = frame.frame_element().bounding_box()
        info["ukuran"] = kotak and {"w": kotak["width"], "h": kotak["height"]}
        if kotak and kotak["width"] > 0 and kotak["height"] > 0:
            frame.frame_element().screenshot(path=str(folder / f"frame{i}.png"))
        else:
            info["catatan"] = "frame tak terlihat (0x0), tanpa screenshot"
    except Exception as err:
        info["catatan"] = f"screenshot frame gagal: {str(err)[:120]}"
    return info


def rekam_state(page, folder, log):
    """Simpan semua frame dari tab ke folder. Kembalikan daftar info per frame."""
    folder.mkdir(parents=True, exist_ok=True)
    frames = page.frames[:MAX_FRAME]
    hasil = [info_frame(page, i, f, folder, log) for i, f in enumerate(frames)]
    (folder / "ringkasan.json").write_text(
        json.dumps({"url_tab": page.url, "frame": hasil}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    for h in hasil:
        log.info("%s frame %d (%s): %s elemen, tombol nav %d", folder.name, h["frame"],
                 h["url"], h.get("jumlah_elemen", "?"), len(h.get("tombol_nav", [])))
    return hasil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["mock", "real"], default="real")
    parser.add_argument("--attach", required=True, metavar="URL_CDP")
    parser.add_argument("--state", action="append", help="nama state; boleh diulang")
    args = parser.parse_args()
    states = [nama_state_valid(s) for s in (args.state or STATE_BAWAAN)]
    if len(states) > MAX_STATE:
        raise SystemExit(f"Maksimal {MAX_STATE} state.")

    log = setup_logger()
    akar = LOG_DIR / f"diagnosa_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.attach)
        for nama in states:
            input(f"Pindah ke state '{nama}' di Chrome, tunggu halaman selesai dimuat, "
                  "lalu tekan Enter: ")
            rekam_state(cari_tab(browser, args.target), akar / nama, log)
    log.info("Selesai. Hasil di %s", akar)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        setup_logger().error("diagnosa berhenti: %s", err)
        sys.exit(1)

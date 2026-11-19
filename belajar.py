"""Mode belajar: kalau bot tak tahu cara mengerjakan halaman, pengguna mengerjakannya sendiri sementara
bot merekam (klik, isian, seret) dan menyimpan HTML sebelum/sesudah ke logs/. Rekaman dipakai untuk
membuat handler baru. Hanya mengamati: tidak mengklik, tidak mengisi, tidak membaca kelas hasil jawaban."""
import json
from datetime import datetime

from helpers import LOG_DIR, setup_logger

MAX_AKSI = 300  # batas kejadian per jeda; lewat dari ini tidak dicatat lagi
MAX_NILAI = 80  # batas panjang teks isian/outerHTML yang disimpan per kejadian
JS_PASANG = """([maks, nilai]) => {
  const jalur = (e) => { const p = []; for (let n = e; n && n.nodeType === 1 && p.length < 5; n = n.parentElement) {
    const k = [...n.classList].slice(0, 2).map((c) => '.' + c).join('');
    p.push(n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + k); } return p.join(' < '); };
  window.__rekamManusia = [];
  if (window.__rekamLepas) window.__rekamLepas();  // pasang ulang bersih, jangan dobel
  const t0 = Date.now(), pasang = [];
  window.__rekamLepas = () => pasang.forEach(([j, f]) => document.removeEventListener(j, f, true));
  for (const jenis of ['click', 'mousedown', 'mouseup', 'input', 'change', 'dragstart', 'drop', 'keydown']) {
    const f = (ev) => {
      const a = window.__rekamManusia;
      if (a.length >= maks) return;
      const e = ev.target;
      a.push({t: Date.now() - t0, jenis, jalur: jalur(e), teks: (e.innerText || '').slice(0, nilai),
              html: (e.outerHTML || '').slice(0, nilai * 4),
              nilai: ('value' in e && e.type !== 'password') ? String(e.value).slice(0, nilai) : null,
              kunci: jenis === 'keydown' ? ev.key : null});
    };
    document.addEventListener(jenis, f, true);
    pasang.push([jenis, f]);
  }
}"""


def rekam_dan_tunggu(page, alasan, tunggu):
    """Simpan keadaan awal, pasang perekam, panggil tunggu() (blok sampai pengguna selesai), lalu simpan
    keadaan akhir dan daftar aksi. Kembalikan awalan nama file. Gagal merekam tidak menghentikan bot."""
    from ambil_html import simpan  # di sini, bukan di atas: ambil_html mengimpor bot, bot mengimpor modul ini
    log = setup_logger()
    awalan = "belajar_" + datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        simpan(page, f"{awalan}_sebelum", log)
        page.evaluate(JS_PASANG, [MAX_AKSI, MAX_NILAI])
    except Exception as err:
        log.error("Perekam gagal dipasang (lanjut tanpa rekaman): %s", err)
    tunggu()
    aksi = []
    try:
        aksi = page.evaluate("() => window.__rekamManusia || []")
        simpan(page, f"{awalan}_sesudah", log)
    except Exception as err:  # mis. halaman berpindah saat pengguna bekerja: perekam ikut hilang
        log.error("Rekaman akhir gagal dibaca: %s", err)
    (LOG_DIR / f"{awalan}_aksi.json").write_text(json.dumps(
        {"alasan": alasan, "url": page.url.split("?")[0], "aksi": aksi}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    log.info("Rekaman belajar: %d aksi disimpan di logs/%s_*", len(aksi), awalan)
    return awalan

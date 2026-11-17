# HANDOFF engdis-bot (tahap 2, worktree `tahap-2-elemen`)

Ditulis 2026-11-18. Branch `worktree-tahap-2-elemen`. Kerja HANYA di worktree
`~/engdis-bot/.claude/worktrees/tahap-2-elemen/`; root `~/engdis-bot/` (tahap 1) jangan disentuh.
Python: `~/engdis-bot/.venv/bin/python` (venv hanya ada di root; dipakai untuk menjalankan saja).

## 1. Sudah dikerjakan dan terbukti

| Hal | Bukti |
|---|---|
| `diagnosa.py` (baca-saja): rekam per state/frame, mode `--pantau` | commit `9d4a72e`, `3727bf1` |
| Fase 2: `jalankan_pelajaran` mulai dari dashboard/area belajar, pilih unit, lesson, step lewat dropdown, Test/Quiz/Exam tidak disentuh | commit `5b98ce0` |
| Seluruh uji otomatis | `test_mock.py`: 55 LULUS, exit 0 (dijalankan sebelum commit `5b98ce0`) |
| Rekaman situs asli satu unit (28 tampilan) | `logs/diagnosa_20261117-204430/pantau_001..028` (logs/ tidak ikut git) |

Temuan struktur situs asli (dari rekaman, bukan tebakan):
- Area belajar = halaman terpisah `/Runtime/learningArea.html` (BUKAN iframe, BUKAN route `#/`). Tanpa `frame_locator`.
- Dashboard `/smktelkommlg#/home`: kartu `.home__unitIW` (teks "Completed!" kalau selesai), tombol `a.layout__btnAction` Continue.
- Penanda selesai soal: `.learning__tasksNav_task--done`. Progres lesson/step di dropdown:
  `.progressBar__progress--done|inProgress|notStarted`.
- Header: `#learning__dropDownListTitleW_lessons|steps`, daftar `#learning__dropDownListW_lessons|steps`,
  item `.learning__dropDownList_item` (`--current` = aktif). Ikon rumah `#sitemenu__itemHome`.
- Nama step tidak seragam antar lesson (Explore/Practice/Test, Prepare/Explore/Practice, Interact 1).
- Layar intro step: `.learning__tasksNav_pager_intro.learning__tasksNav_task--current`.
- Next `a.tasksBtnext`, Check `#CheckAnswer` (li di toolbar bawah).
- Jenis soal terekam: pilihan ganda (`input.layout__radio`, `label.prMCQ__answerLabel`, beberapa
  pertanyaan per halaman, `name` unik per radio: `question-N_answer-M`); dropdown KUSTOM
  (`.prFITB__DDLOptionsW` > `.DDLOptions__selected` diklik -> `.DDLOptions__list` > `.DDLOptions__listItem`,
  BUKAN `<select>`); cloze seret (`.prCLZ__regContainer .dndZone`, bank `.prCLZ__wordsBankWrapper .dnditem`);
  pencocokan seret (`.prMT_T2T__*`, `.dndZone`, `.dnditem`); suara+pilihan (`.answersWrapper.mcq.webRtc`,
  `.lessonMultipleAnswer`); Start/percakapan (`.speakingInteractButtonWrapper`); video/audio (`.learning__RAMRButton--play`).

## 2. Keputusan pemilik akun (mengikat)
- Step **Test** (bernilai) dikerjakan pemilik akun sendiri; bot tidak boleh menyentuhnya.
- Jawaban salah tidak masalah; `--done` tetap bertambah. Tujuan: selesai, bukan benar.
- Tidak pernah menyentuh See Answer. Kelas hasil (`correct`, `--incorrect`, `checkResult`) JANGAN dibaca
  atau dipakai untuk mencoba ulang (itu sama dengan mengintip kunci).
- Urutan fase tetap: 2 (selesai) -> 3 -> 4. Tidak pakai jalur API.

## 3. Belum selesai / belum diuji
Belum terbukti di `ed.engdis.com` asli (hanya diuji di tiruan `mock_kursus.html`, `mock_real.html`):
- klik kartu unit, ikon rumah `#sitemenu__itemHome`, apakah dropdown menutup sendiri setelah memilih,
  dan perilaku Next di akhir step/lesson.
- Handler soal (Fase 3), belum dikerjakan:
  1. Ganti `isi_dropdown` (select biasa) dengan handler dropdown kustom `.DDLOptions__*`.
  2. `pilih_radio` per pertanyaan (kelompokkan `question-N`), bukan hanya radio pertama.
  3. Handler pencocokan `prMT_T2T__*`.
  4. Regex `TIDAK_DIDUKUNG`: hapus `Drag` (cloze sudah ada handler); biarkan hanya yang belum ada handler.
  5. Isian teks (`textarea`/`[contenteditable]`) dan mikrofon/webRtc: belum pernah terekam; kalau tak
     bisa diverifikasi, berhenti dengan screenshot + log (tidak menebak, tidak skip).
  6. SEL disamakan dengan HTML asli (lihat rekaman di atas). Dua kandidat selector ambigu: tanya pemilik.
- Fase 4: uji iteratif di situs asli (kirim log + screenshot tiap berhenti); target 1 lesson penuh.
- Bug `cari_tab` "unhashable dict": TIDAK ada di worktree ini (sudah `CIRI_HALAMAN[target]`). Kemungkinan
  salinan lain (mis. folder Windows) masih versi lama; pemilik perlu menyamakan salinan yang dijalankan.
- Catatan: `tunggu_stabil` dan `--pantau` memakai `wait_for_timeout` (polling); aturan "tanpa sleep tetap"
  perlu dirapikan di Fase 3.

## 4. Commit terakhir dan blok yang belum dijalankan
Commit terakhir yang diharapkan: HEAD di branch `worktree-tahap-2-elemen` (commit HANDOFF ini di atas `5b98ce0`).
Belum di-push. Blok siap tempel:

```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git log --oneline -5
git push -u origin worktree-tahap-2-elemen
```

## 5. Cek awal untuk sesi baru
```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git status --short && git log --oneline -3
~/engdis-bot/.venv/bin/python test_mock.py | grep -c LULUS   # harapan: 55, tanpa GAGAL
```
Aturan yang berlaku: ikuti `~/.claude/CLAUDE.md`. Perubahan perilaku kode wajib disertai uji otomatis;
file banyak diubah atomik (skrip patch Python); commit jujur (tulis yang belum terbukti).

## 6. Prompt pembuka sesi baru (simpan)
```
Lanjutkan proyek ~/engdis-bot di worktree .claude/worktrees/tahap-2-elemen/ (jangan sentuh root).
Baca HANDOFF.md lebih dulu. Fase 1 dan 2 selesai (commit 5b98ce0, test_mock 55 lulus).
Mulai Fase 3: handler soal sesuai bagian 3 HANDOFF (dropdown kustom, pilihan ganda per pertanyaan,
pencocokan, cloze, perbarui TIDAK_DIDUKUNG). Aturan: Test dikerjakan manual oleh saya, tidak pernah
menyentuh See Answer, jawaban salah tidak masalah, tanpa sleep tetap, gagal = screenshot + log,
keputusan ambigu: berhenti dan tanya. Commit tiap bagian selesai.
```

# HANDOFF engdis-bot (tahap 2, worktree `tahap-2-elemen`)

Ditulis 2026-11-18, diperbarui saat tutup sesi 2026-11-19 (Fase 3 + perbaikan hasil 3 uji pertama di situs asli; semua masih hanya lulus di tiruan). Branch `worktree-tahap-2-elemen`. Kerja HANYA di worktree
`~/engdis-bot/.claude/worktrees/tahap-2-elemen/`; root `~/engdis-bot/` (tahap 1) jangan disentuh.
Python: `~/engdis-bot/.venv/bin/python` (venv hanya ada di root; dipakai untuk menjalankan saja).

## 1. Sudah dikerjakan dan terbukti

| Hal | Bukti |
|---|---|
| `diagnosa.py` (baca-saja): rekam per state/frame, mode `--pantau` | commit `9d4a72e`, `3727bf1` |
| Fase 2: `jalankan_pelajaran` mulai dari dashboard/area belajar, pilih unit, lesson, step lewat dropdown, Test/Quiz/Exam tidak disentuh | commit `5b98ce0` |
| Seluruh uji otomatis | `test_mock.py`: 55 LULUS, exit 0 (dijalankan sebelum commit `5b98ce0`) |
| Fase 3: dropdown kustom (`09343db`), pilihan ganda per pertanyaan (`72e3b40`), pencocokan + penjaga suara/isian teks (`8438701`), refactor `tunggu_stabil` tanpa sleep Python + `isi_seret` (`b67aaa5`) | `test_mock.py`: 61 LULUS, exit 0 (di tiruan saja) |
| `bot.py --buka`: membuka Chromium WSL (port 9222, profil `~/.engdis-chrome-profil`), login manual, Enter, lalu kerja | `f121e29`; uji di tiruan (headless) |
| Perbaikan dari uji situs asli: URL awal `smktelkommlg#/`, timeout area 45 dtk, step Test tanpa status = manual, `daftar_terbuka` pakai posisi atas, `buka_kunci_lesson`, mode `--hanya-baca` | `bdb2010`, `85b4576`, `7dfda14`, `901041f`, `00e3fde`, `8655352`; `test_mock.py`: 73 LULUS, exit 0 (tiruan saja) |
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
- Handler soal (Fase 3) SUDAH ditulis dan lulus di tiruan, tetapi semuanya belum pernah jalan di situs asli:
  1. Dropdown kustom `.prFITB__DDLOptionsW`: klik `.DDLOptions__selected`, pilih `.DDLOptions__listItem`
     pertama. Asumsi belum terbukti: elemen terpilih yang kosong punya ukuran (terlihat) dan daftar
     menutup sendiri sesudah memilih (bot memeriksa daftar hilang; kalau tidak, berhenti + screenshot).
  2. Pilihan ganda: opsi pertama tiap `.prMCQ__qaSet`, klik `label[for=id]`. Radio di luar qaSet = berhenti.
  3. Pencocokan `prMT_T2T__*` dan cloze: `isi_seret` (mouse bertahap). Belum terbukti dengan Dragula asli.
  4. `TIDAK_DIDUKUNG` kini `Type|Write|Fill|Put|Record|Say|Speak|Order` (Drag/Match sudah ada handler).
  5. Penjaga: `.answersWrapper.webRtc` dan textarea/contenteditable/input teks di luar
     `#DictionaryPanelContainer` -> berhenti sebelum mengklik apa pun. Kalau panel Dictionary asli punya
     input teks di luar kontainer itu, bot akan berhenti salah (gagal tertutup); kirim screenshot-nya.
  6. Soal suara (webRtc, pantau_008) tetap tidak ditangani; isian teks belum pernah terekam.
- Temuan uji situs asli 2026-11-18 (DOM dibaca lewat CDP, baca saja): judul daftar lesson berkelas
  `learning__dropDownListTitleW--disabled` selama step aktif = Test (daftar lesson terkunci, daftar step
  tidak); daftar lesson tertutup berada di y=-304 (tinggi 372), terbuka di sekitar y=62; step Test tidak
  punya progress bar. Perbaikan: `buka_kunci_lesson`, `daftar_terbuka` (posisi atas), step Test = "manual".
  Unit 4 punya lesson ke-7 "7. Sports" (notStarted), isinya belum diketahui: jalankan `--hanya-baca` dulu.
  Belum terbukti: ikon rumah bisa diklik dari intro Test; pindah ke step non-Test membuka kunci.
- STATUS UJI SITUS ASLI (3 percobaan 2026-11-18): bot sampai membuka unit 4 dan memilih lesson, belum
  pernah menjawab satu soal pun di situs asli. Uji kering `--hanya-baca` setelah perbaikan terakhir
  BELUM dijalankan. Unit 4 pemilik akun tinggal Test (harus dilewati bot, lanjut ke unit 5).
  Jendela Chromium terakhir ada di layar "Start Test" unit 4 (tidak disentuh bot).
- Fase 4: uji iteratif di situs asli (kirim log + screenshot tiap berhenti); target 1 lesson penuh.
- Bug `cari_tab` "unhashable dict": TIDAK ada di worktree ini (sudah `CIRI_HALAMAN[target]`). Kemungkinan
  salinan lain (mis. folder Windows) masih versi lama; pemilik perlu menyamakan salinan yang dijalankan.
- Catatan: `tunggu_stabil` kini polling di sisi halaman (`wait_for_function`, tanpa sleep Python).
  `--pantau` di `diagnosa.py`/`ambil_html.py` masih memakai `wait_for_timeout` (alat diagnosa, bukan bot).

## 4. Commit terakhir dan blok yang belum dijalankan
Commit terakhir yang diharapkan: HEAD di branch `worktree-tahap-2-elemen` (commit "HANDOFF tutup sesi" di atas
`8655352`). Semua commit sudah di-push ke origin (`mahatsafa/ed`); tidak ada blok commit tertunda. Cek:

```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git fetch -q && git status -sb | head -2   # harapan: tidak ada 'ahead'
```

## 5. Cek awal untuk sesi baru
```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git status --short && git log --oneline -3
~/engdis-bot/.venv/bin/python test_mock.py | grep -c LULUS   # harapan: 73, tanpa GAGAL (butuh ~2 menit)
```
Aturan yang berlaku: ikuti `~/.claude/CLAUDE.md`. Perubahan perilaku kode wajib disertai uji otomatis;
file banyak diubah atomik (skrip patch Python); commit jujur (tulis yang belum terbukti).

## 6. Prompt pembuka sesi baru (simpan)
```
Lanjutkan proyek ~/engdis-bot di worktree .claude/worktrees/tahap-2-elemen/ (jangan sentuh root).
Baca HANDOFF.md lebih dulu. Fase 1-3 selesai di tiruan (test_mock 73 lulus); 3 uji di situs asli
menghasilkan perbaikan navigasi (daftar lesson terkunci saat step Test). Langkah berikutnya: saya
jalankan `bot.py --target real --buka --hanya-baca` dan menempel baris RENCANA / error + screenshot
logs/. Periksa rencananya (tidak ada step Test, isi lesson "7. Sports" unit 4), lalu jalan tanpa
--hanya-baca dan perbaiki satu per satu. Aturan: Test dikerjakan manual oleh saya dan dilewati bot
(unit yang tinggal Test dilewati, lanjut unit berikutnya), tidak pernah menyentuh See Answer, jawaban
salah tidak masalah, tanpa sleep tetap, gagal = screenshot + log, keputusan ambigu: berhenti dan
tanya. Commit tiap bagian selesai setelah test_mock lulus.
```

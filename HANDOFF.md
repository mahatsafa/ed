# HANDOFF engdis-bot (tahap 2, worktree `tahap-2-elemen`)

Ditulis 2026-11-18, diperbarui saat tutup sesi 2026-11-19 (sesi ke-3: bot mulai menjawab soal di situs asli; mode belajar; handler dikte, bacaan, Reminder). Branch `worktree-tahap-2-elemen`. Kerja HANYA di worktree
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
| Sesi 3 (2026-11-19), semua di-push; `test_mock.py` 99 LULUS, exit 0 (tiruan/potongan HTML saja) | |
| Tutup daftar lewat overlay; unit yang kartunya berbalik dibuka lewat lesson pertama | `f82c28b` |
| Klik ikon rumah: batas tunggu 30 dtk (navigasi lambat) | `10f1788` |
| Halaman bacaan (artikel tanpa soal): cukup Next | `18cd6af` |
| Mode belajar (`belajar.py`): halaman tak dikenal -> jeda, pengguna mengerjakan sendiri, bot merekam aksi + HTML sebelum/sesudah ke `logs/belajar_*`, Enter, lanjut | `9e6b1a4` |
| Soal dikte (`prOpenEnded`): isi tiap textarea lalu Check; batas tunggu pindah lesson 45 dtk | `6351a90` |
| Jendela Reminder (kerjakan aktivitas N atau Continue/lewati, `lewat_step`); video: tunggu tombol putar | `46f281e` |
| Di situs asli bot SUDAH menjawab: pencocokan, cloze, dropdown (unit 4, lesson 7, step Practice) | log jalan 08:43-08:44 |

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
Terbukti di situs asli (dari log jalan 2026-11-19): pindah unit/lesson/step, pencocokan, cloze (seret), dropdown
kustom, perekaman mode belajar. Belum ada satu step pun yang terbukti selesai penuh.

Belum terbukti di situs asli (hanya lulus di tiruan):
- Handler dikte (`isi_teks_bebas`, jawaban "a"): apakah aktivitas dikte tercatat selesai setelah Check.
- Handler Reminder (`selesaikan_reminder`): pager nomor (`.learning__tasksNav_tasksW .learning__tasksNav_task`)
  bisa diklik; pencarian teks "Stay in this step" / "Continue" cocok dengan DOM asli; Continue melewati step
  tanpa efek samping. DOM jendela Reminder belum pernah terbaca (sudah tertutup saat dicek).
- Video: tombol putar `.learning__RAMRButton--play` muncul terlambat; bot kini menunggunya (maks 3 dtk).
  Belum dilihat jalan ulang di situs asli (kegagalan terakhir: unit 5 lesson 1 step Explore halaman 2).
- Pencocokan: setelah Check, tanda benar/salah muncul tetapi penanda selesai `.learning__tasksNav_task--done`
  tidak bertambah; penyebab belum diketahui (kelas hasil jawaban tidak boleh dibaca, jadi jangan diselidiki lewat itu).
- Jendela kartu kosakata (1/10) di step Explore lesson 7: pernah menghentikan bot; bentuknya sudah ada di
  rekaman layar tetapi handler belum ditulis. Mode belajar akan merekamnya kalau muncul lagi.
- Soal suara (webRtc) tetap berhenti; isian teks selain dikte tetap berhenti (gagal tertutup).
- Unit 9 lesson 1: step "5. Let's review" tanpa progress bar (mirip Test). KEPUTUSAN PEMILIK AKUN BELUM ADA:
  dikerjakan manual dan dilewati bot, atau dikerjakan bot? Sampai ada keputusan, bot berhenti di sana.
- Mode belajar: kalau halaman berpindah saat pengguna bekerja, perekam hilang (HTML sesudah tetap tersimpan).
- Fase 4: uji iteratif di situs asli; target 1 lesson penuh.
- Kredensial: ada di `.env` (di-ignore git). Password pernah tertulis di chat; sebaiknya diganti.
- Catatan operasional: jangan jalankan dua sesi/dua `test_mock.py` bersamaan di worktree yang sama (port
  9333/9444 bentrok, hasil uji jadi naik-turun); jangan menjalankan bot dan uji bersamaan.
  Di shell pemilik akun `ls` adalah alias ke `eza` (opsi `-t` berbeda): pakai `command ls`.
- `tunggu_stabil` polling di sisi halaman; `--pantau` di diagnosa/ambil_html masih memakai `wait_for_timeout`.

## 4. Commit terakhir dan blok yang belum dijalankan
Commit terakhir: `46f281e` (ditambah commit HANDOFF ini). Semua di-push ke origin (`mahatsafa/ed`);
tidak ada blok commit tertunda. Cek:

```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git fetch -q && git status -sb | head -2   # harapan: tidak ada 'ahead'
```

## 5. Cek awal untuk sesi baru
```bash
cd ~/engdis-bot/.claude/worktrees/tahap-2-elemen
git status --short && git log --oneline -3
ps -eo args | grep -E "test_mock|bot.py" | grep -v grep | wc -l   # harapan: 0
~/engdis-bot/.venv/bin/python -u test_mock.py > logs/test_mock_terakhir.txt 2>&1   # ~10 menit: jalankan di latar belakang
grep -c LULUS logs/test_mock_terakhir.txt; grep -c GAGAL logs/test_mock_terakhir.txt   # harapan: 141 dan 0
```
Aturan yang berlaku: ikuti `~/.claude/CLAUDE.md`. Perubahan perilaku kode wajib disertai uji otomatis;
banyak file diubah atomik (skrip patch Python); commit jujur (tulis yang belum terbukti).
Alur kerja yang berhasil: pemilik akun menjalankan bot, menempel log + screenshot; saya baca
`logs/belajar_*_aksi.json` / DOM (baca saja lewat CDP port 9222), tulis handler + uji, commit, push.

## 6. Prompt pembuka sesi baru (simpan)
```
Lanjutkan proyek ~/engdis-bot di worktree .claude/worktrees/tahap-2-elemen/ (jangan sentuh root).
Baca HANDOFF.md lebih dulu. Sesi lalu: bot sudah menjawab pencocokan, cloze, dropdown di situs asli;
ditambah mode belajar (bot merekam saat saya mengerjakan halaman yang tak dikenal), handler dikte,
bacaan, jendela Reminder, soal seret (klasifikasi), menulis, audio/video sampai habis (test_mock 138 lulus,
commit d4687c0). Bot kini kujalankan sendiri di Chromium yang sudah login (`--attach http://127.0.0.1:9222`),
Lesson 1 dan 2 selesai, Lesson 3 Practice berhenti di soal suara. Baca HANDOFF.md bagian 7. Keputusan yang
menunggu: cara menangani soal suara (mikrofon); juga step "Let's review" unit 9 (tanpa progress bar). Aturan: Test dikerjakan manual oleh saya dan dilewati bot, tidak pernah
menyentuh See Answer atau membaca kelas hasil jawaban, jawaban salah tidak masalah, tanpa sleep tetap,
gagal = screenshot + log, keputusan ambigu: berhenti dan tanya. Jangan jalankan dua sesi bersamaan di
worktree ini. Commit tiap bagian selesai setelah test_mock lulus.
```

## 7. Pembaruan sesi 2026-11-19 (bot dijalankan sendiri di situs asli, ±12 jalan)
Cara jalan: `bot.py --target real --attach http://127.0.0.1:9222 > logs/jalan_real.txt` (Chromium sudah login di
port 9222). Tanpa terminal interaktif bot berhenti (gagal tertutup) di halaman yang tak dikenal.

Terbukti di situs asli (log + screenshot, bukan tebakan):
- Handler: video/audio diputar sampai habis; dropdown, cloze, pencocokan, pilihan ganda, menulis (TinyMCE, 14 kata),
  klasifikasi `prCl` (item dibagi ke kolom) semuanya `OK: tugas tercatat selesai`; Reminder bernomor, jamak,
  dan basi ditangani; Lesson 1 dan 2 selesai, step Test dilewati.
- Pelajaran dari situs: kartu Reminder ada di iframe `MsgPage.html` dan memuat belakangan (kartu sempat kosong);
  status daftar step terlambat diperbarui (±40 dtk) sedangkan penanda `--done` di pager andal; MCQ yang dijawab
  salah tetap dihitung selesai; audio `#syncAudioPlayer` dipakai ulang antar halaman dan TIDAK memicu `ended`
  (dipotong ±0,8 dtk sebelum akhir lalu dimuat ulang); meninggalkan step yang belum selesai memunculkan Reminder
  "complete all the activities" (Continue/Stay); halaman bacaan punya `button#sitemenu__openMenuBtn`.
- Jangan meninggalkan tab di tengah step atau dengan Reminder terbuka saat bot dijalankan (bot kini membersihkannya).

Belum terbukti di situs asli: handler `prTextToPic` (kata ke gambar) dan penanganan Reminder "all the activities"
di Next halaman terakhir; peringatan "tak terbukti selesai" untuk MCQ salah hanyalah penanda pager yang tak andal.

KEPUTUSAN MENUNGGU (pemilik akun): soal suara (`.answersWrapper.webRtc`, Lesson 3 Practice halaman 4/5).
Bukti: klik pilihan tak berpengaruh; tombol Start nonaktif; sesi Speech Recognition tak pernah terbentuk tanpa mikrofon.
- A (rekomendasi): dikerjakan manual oleh pemilik akun; bot berhenti di sana, lalu dilanjutkan.
- B: bot melewati (Continue) dan menerima step tidak pernah `done`.
- C: mikrofon virtual (flag Chromium + file audio ucapan); ketergantungan baru, perlu persetujuan.
Posisi terakhir: Lesson 3, Step 2 Practice, halaman 4/5 (soal suara); Lesson 1 dan 2 sudah done.

### 7b. Tambahan akhir sesi 2026-11-19
Selesai sejak 7: soal suara (webRtc) = cukup direkam (`rekam_suara`: tunggu Start aktif, klik, tunggu "Try again";
situs merekam otomatis ±8 dtk; keputusan pemilik akun: isi ucapan tak dinilai). Mikrofon laptop terlihat di Chromium
(izin granted; perangkat Default dan RDP Source). Lesson 3 Practice dianggap selesai oleh situs.

MASALAH TERBUKA 1 (perlu tindakan pemilik akun): audio keluaran Chromium macet global setelah sesi mikrofon.
Bukti: AudioContext di tab kosong maju 0,000 dtk per 1 dtk; /mnt/wslg/pulseaudio.log penuh
"rdp-source: q overrun, queuing locally"; di Lesson 4 Prepare `#syncAudioPlayer` paused=false tetapi currentTime=0
(bot gagal di `video_terputar`). Percobaan mematikan proses AudioService Chromium ditolak pemeriksa izin; cadangan:
`wsl --shutdown` lalu buka Chromium lagi (login mungkin diulang). Uji pemulihan: jam AudioContext harus maju ±1 per dtk.
Kalau terulang tiap kali soal suara: pertimbangkan mematikan keluaran audio Chromium (flag di bot.py buka_chrome) agar
jam media tak bergantung pada perangkat audio; perlu persetujuan pemilik akun (mengubah cara Chromium dibuka).

MASALAH TERBUKA 2: step "Interact" (dialog peran) belum punya handler. Struktur (dari rekaman): `.speakingInteract`,
`a.chooseCaracterArrow` kiri/kanan untuk memilih karakter, `.speakingInteractPanelsWrapper a.button.continue` (Start,
nonaktif sampai karakter dipilih/sesi siap), `.recordingPanelSentence` (kalimat bernomor, `.statusIcon`), tombol
`startAgain` (Restart). Bot sekarang berhenti di sini (gagal tertutup); langkah berikut: amati alurnya saat audio
berfungsi (klik panah, Start, tunggu semua kalimat selesai) lalu tulis handler + uji. Reminder aktivitas 1 muncul
bila dilewati.

Posisi terakhir: Lesson 3 selesai sampai Practice; Step 3 Interact 1 belum; Lesson 4 Prepare menunggu audio pulih.
Commit terakhir di kode: lihat `git log -3`.

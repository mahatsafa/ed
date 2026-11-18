# engdis-bot

Tugas sekolah TKJ: bot otomatisasi browser dengan Python + Playwright.
Latihan dilakukan di `mock.html` (halaman buatan sendiri). Bot ke situs asli hanya dijalankan
setelah guru mengizinkan.

## Cara menjalankan

```bash
cd ~/engdis-bot
.venv/bin/python test_mock.py
.venv/bin/python bot.py --target mock --headed
```

## Penjelasan file (untuk presentasi)

| File | Fungsinya |
|---|---|
| `.env` | Menyimpan username dan password. Tidak ikut GitHub karena ada di `.gitignore`. |
| `.env.example` | Contoh isi `.env` tanpa data asli. Aman di-push. |
| `.gitignore` | Daftar file yang tidak boleh masuk GitHub: `.env`, `logs/`, `.venv/`. |
| `helpers.py` | Fungsi kecil yang dipakai bersama. |
| `login.py` | Fungsi login. |
| `tugas.py` | Satu fungsi per persyaratan tugas (video, jawaban, huruf kosong, teks, mikrofon, Start, header). |
| `bot.py` | Alur utama: baca `.env`, buka browser, panggil login. |
| `mock.html` | Halaman latihan yang meniru elemen tugas. |
| `test_mock.py` | Uji otomatis untuk login. |
| `logs/` | Hasil log (`bot.log`) dan screenshot saat gagal. |

### helpers.py
- `setup_logger()`: membuat catatan langkah ke layar dan ke `logs/bot.log`.
- `wait_visible(page, locator, name)`: menunggu elemen muncul. Kalau tidak muncul dalam
  10 detik, catat error, simpan screenshot, lalu error diteruskan.
- `click(page, locator, name)`: mengklik elemen. Playwright menunggu elemen siap sendiri.
- `screenshot_on_fail(page, name)`: menyimpan gambar layar ke `logs/`.

### tugas.py
Setiap fungsi melakukan satu aksi lalu **memeriksa hasilnya** (bukan hanya mengklik):
- `putar_video`: klik video, pastikan video benar-benar berjalan (tidak berhenti, waktu maju).
- `pilih_jawaban`: pilih jawaban, klik Submit, pastikan "Completed task" muncul dan reminder tidak.
- `isi_huruf_kosong`: klik pilihan kata sampai semua kotak terisi (maksimal sebanyak jumlah kotak).
- `isi_teks`: salin teks pertanyaan ke kolom teks, pastikan isinya sama.
- `klik_mikrofon`: klik mikrofon, pastikan halaman mencatat klik.
- `klik_start`: klik teks pengaktif, tunggu Start aktif, klik Start.
- `klik_header`: klik dua tombol header.
- `jalankan_semua`: menjalankan semuanya berurutan seperti di panduan.

Kalau pemeriksaan gagal, bot mencatat error, menyimpan screenshot ke `logs/`, lalu berhenti.

### Mode attach (bot menempel ke browser yang Anda buka sendiri)
`bot.py --attach http://127.0.0.1:9222` tidak membuka browser baru dan tidak login. Bot mencari
tab yang sudah Anda buka (verifikasi dan login dilakukan manusia), lalu mengerjakan tugas di tab itu.
Mode ini sudah diuji di mock. Untuk situs asli **belum diuji**.

### Uji kering: --hanya-baca
`bot.py --target real --buka --hanya-baca` berpindah unit/lesson/step seperti biasa tetapi TIDAK menjawab
apa pun. Log `RENCANA | unit | lesson | dikerjakan | dilewati (Test)` menunjukkan apa yang akan dikerjakan
bot. Jalankan ini dulu, periksa tidak ada step bernama lain yang sebenarnya ujian, baru jalan biasa.
Situs asli mengunci daftar lesson selama step Test aktif; bot lalu pindah ke step non-Test dulu.

### Mode --buka (paling mudah di WSL)
`bot.py --target real --buka` membuka Chromium di WSL (profil `~/.engdis-chrome-profil`, sesi login
tersimpan), lalu menunggu. Anda login dan buka dashboard di jendela itu, tekan Enter di terminal, bot
mengerjakan. Port 9222 sudah dipakai browser lain = dipakai ulang. Chromium tidak ditutup bot di akhir.

### pelajaran.py (situs asli)
`jalankan_pelajaran` mengerjakan satu halaman soal, klik Next, lalu mengulang:
- Yang dikenali: video (putar), pilihan ganda (opsi pertama tiap pertanyaan `.prMCQ__qaSet`, klik label),
  dropdown kustom `.prFITB__DDLOptionsW` (item pertama), cloze dan pencocokan (seret kata dari bank
  berurutan), Start (tunggu aktif lalu klik). Soal selain video/Start di-submit lewat Check Answer.
- Berhenti sebelum mengklik apa pun kalau ada soal suara (`.answersWrapper.webRtc`), isian teks
  (textarea/contenteditable/input teks di luar panel Dictionary), atau instruksi `Type|Write|Fill|Put|
  Record|Say|Speak|Order`. Jawaban dipilih tanpa membaca kunci (benar atau salah tidak dibaca).
- Berhenti sendiri kalau jenis soal tidak dikenal, Next tidak mengubah halaman, atau batas 30 halaman.
- Tidak pernah menyentuh See Answer (kunci jawaban) dan tidak membaca kunci.
- Tombol header yang diklik: Dictionary dan Help (asumsi; ubah `HEADER_ASLI`).
- Belum ada: isian teks dan soal suara (selector belum terekam); bot berhenti dengan screenshot.
Diuji di `mock_real.html`, halaman tiruan dengan selector situs asli (bukan situs asli).

Auto-navigasi (`jalankan_pelajaran`): mulai dari dashboard (atau area belajar), buka unit pertama
yang belum "Completed!", lalu lesson dan step pertama yang belum selesai (status dari dropdown:
`progressBar__progress--done/inProgress/notStarted`), kerjakan halaman + Next, ulangi sampai semua
unit selesai. Layar intro step langsung di-Next. **Step bernama Test/Quiz/Exam tidak pernah dikerjakan
bot** (dikerjakan pemilik akun sendiri); judul step tak terbaca dianggap Test. Berhenti kalau
jenis soal tak dikenal atau tidak ada kemajuan. Diuji di `mock_kursus.html` (tiruan dashboard + area
belajar); belum dijalankan di situs asli.

### login.py
- `SELECTORS`: daftar selector tiap target. Target `real` masih kosong (menunggu HTML
  dari form login asli), jadi bot berhenti dan tidak menebak.
- `mask(text)`: menyamarkan username di log, misalnya `54*****10`.
- `login(...)`: buka halaman, isi username dan password, klik Masuk, lalu menunggu elemen
  yang hanya muncul setelah login. Password tidak pernah ditulis ke log.

### bot.py
- `load_credentials()`: membaca `.env` dengan python-dotenv. Kalau kosong, bot berhenti.
- `main()`: membaca argumen (`--target mock|real`, `--headed`), membuka Chromium, menjalankan
  login, dan menutup browser di `finally`.

## Menjalankan di Windows (mode attach, PowerShell)
Folder: `C:\Users\<nama>\engdis-bot`. Mode attach tidak memakai `.env` dan tidak login.

```powershell
# 1. Setup sekali saja
cd $HOME\engdis-bot
$py = "$HOME\AppData\Local\Programs\Python\Python313\python.exe"
& $py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

```powershell
# 2. Buka Chrome dengan port debug (profil terpisah, wajib untuk Chrome terbaru)
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$prof = "$HOME\chrome-tugas"
& $chrome --remote-debugging-port=9222 --user-data-dir=$prof https://ed.engdis.com
# Lalu SECARA MANUAL: centang verifikasi, login, buka halaman soal.
```

```powershell
# 3. Jalankan bot di tab itu
cd $HOME\engdis-bot
.\.venv\Scripts\python bot.py --target real --attach http://127.0.0.1:9222
```

`ambil_html.py` hanya membaca halaman (tanpa klik) dan menyimpan strukturnya ke `logs/`,
dipakai untuk mencocokkan selector asli. Tutup Chrome itu setelah selesai (port debug terbuka).

Mode pantau: tambahkan `--pantau`. Pindah soal manual di Chrome; setiap soal baru (isi halaman
berubah dan stabil) disimpan otomatis sebagai `<nama>01_...`, `<nama>02_...` (maksimal 40).
Ctrl+C untuk berhenti.

## Konsep singkat
- **Selector**: alamat sebuah elemen di halaman, misalnya `#username` (elemen dengan id username).
- **Wait**: menunggu elemen siap, bukan jeda waktu tetap (`sleep`). Locator Playwright
  melakukannya otomatis.
- **Event click**: kejadian saat elemen diklik. Bot memicunya lewat `locator.click()`,
  dan halaman bereaksi seperti diklik manusia.

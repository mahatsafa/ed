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

## Konsep singkat
- **Selector**: alamat sebuah elemen di halaman, misalnya `#username` (elemen dengan id username).
- **Wait**: menunggu elemen siap, bukan jeda waktu tetap (`sleep`). Locator Playwright
  melakukannya otomatis.
- **Event click**: kejadian saat elemen diklik. Bot memicunya lewat `locator.click()`,
  dan halaman bereaksi seperti diklik manusia.

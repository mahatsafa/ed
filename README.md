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

## Konsep singkat
- **Selector**: alamat sebuah elemen di halaman, misalnya `#username` (elemen dengan id username).
- **Wait**: menunggu elemen siap, bukan jeda waktu tetap (`sleep`). Locator Playwright
  melakukannya otomatis.
- **Event click**: kejadian saat elemen diklik. Bot memicunya lewat `locator.click()`,
  dan halaman bereaksi seperti diklik manusia.

# MidasDownloader 🎓

A fast, reliable batch downloader for university entrance admit cards with authentication, rate-limiting, progress bars, and PDF combination support.

Built with **Python 3.11+**, **uv**, **httpx**, **pypdf**, and **Typer**.

---

## ⚡ Quick Run (No Installation Needed)

You can run **MidasDownloader** instantly without cloning or setting up a virtual environment:

### With `uvx` (Fastest):
```bash
# Direct from GitHub:
uvx --from git+https://github.com/aaxyat/MidasDownloader midasdownloader

# Or from PyPI (once published):
uvx midasdownloader
```

### With `pipx`:
```bash
# Direct from GitHub:
pipx run --spec git+https://github.com/aaxyat/MidasDownloader midasdownloader

# Or from PyPI (once published):
pipx run midasdownloader
```

### Or install via `pip`:
```bash
pip install git+https://github.com/aaxyat/MidasDownloader
midasdownloader
```

---

## ✨ Features

- 🪄 **Interactive Guided Wizard:** Run `midasdownloader` (or `uv run midasdownloader`) to guide you through URL entry, authentication, student selection, and custom output folder selection.
- 📑 **Native ERP Report (`.xls`) Support:** Automatically parses student reports (e.g. `report_sample.xls` or `report/Report.xls`), extracting student names and parsing entrance formats like `EN-26-41819` → `41819`.
- 🏷 **Clean File Naming:** Automatically names downloaded admit cards as `StudentName_id.pdf` (e.g. `Aarav_Sharma_41819.pdf`).
- 📄 **Interactive PDF Combination:**
  - **Question 1:** Combine into a single PDF? `[Y/n]`
  - **Question 2:** Include the second page (instructions/rules)? `[y/N]`
  - **Question 3:** Merge both pages together in one file or into separate combined files (`combined_page1.pdf` & `combined_page2.pdf`)?
- 📂 **Custom & Timestamped Output Folder:** Choose a custom folder name inside `out/` (e.g. `out/BIT_Entrance_2083/` or default `out/YYYY-MM-DD_HH-MM-SS/`).
- 🔒 **CodeIgniter Session Auto-Matching:** Automatically extracts and matches the exact `User-Agent` embedded in CodeIgniter's `ci_session` cookie to prevent session expiration drops.
- 🧹 **PDF Header Sanitization:** Automatically strips PHP leading whitespace before `%PDF` bytes for 100% compliant PDF files.
- ⚡ **Fast & Resilient:** Streaming downloads with retry mechanisms on network hiccups and automatic skipping of already-downloaded files.
- 📊 **Rich Progress & Summary:** Terminal progress bar with elapsed time and color-coded result breakdown.

---

## 🚀 Local Project Setup

### 1. Prerequisites & Installation
Ensure you have [uv](https://docs.astral.sh/uv/) installed (or Python 3.11+).

```bash
git clone https://github.com/aaxyat/MidasDownloader.git
cd MidasDownloader
uv sync
```

---

### 2. Configure Authentication Cookie (`.env`)

Create your `.env` file:
```bash
cp .env.example .env
```

Open `.env` and fill in your `ci_session` cookie value:

```env
COOKIE_NAME="ci_session"
ci_session="PASTE_YOUR_CI_SESSION_COOKIE_VALUE_HERE"
```

#### 🔑 How to Get `ci_session` from Google Chrome:
1. Open **Google Chrome** and log in to your college/university portal.
2. Press **`F12`** (or `Ctrl + Shift + I`) to open **Developer Tools**.
3. Go to the **Application** tab.
4. On the left sidebar, expand **Cookies** -> select your portal domain.
5. Find the row named **`ci_session`**, double-click its **Value** column, and copy (`Ctrl + C`) the string.
6. Paste the copied value into `ci_session` in `.env`.

---

### 3. Run the Downloader

#### Option A: Interactive Wizard (Recommended)
Simply run:
```bash
midasdownloader
# or:
uv run midasdownloader
```

1. **Step 1:** Paste your admit card print URL:
   ```text
   https://portal.university.example.edu/entrance/report/prints?entranceid=41819&levelid=3&facultyid=1&programid=30&status=&orgid=undefined&academicbatch=&verified=&isverified=&examcenterid=Y&fromdate=2026-05-27&todate=2026-08-20
   ```
2. **Step 2:** Confirm your cookie (`ci_session` from `.env`).
3. **Step 3:** The wizard automatically detects `report_sample.xls` or your report file:
   ```text
   Found report file report/Report.xls with 53 students. Load from this file? [Y/n]
   ```
   Press **Enter** (Yes), or paste comma-separated IDs directly.
4. **Step 4:** Choose output folder name inside `out/` (e.g. `BIT_Batch_2083` or press Enter for timestamped default).
5. **Step 5:** Confirms pre-flight test check and batch-downloads all admit cards into `out/<folder_name>/`.
6. **Step 6 (Post-Download Combination):**
   - **Q1:** Do you want to combine the downloaded admit cards into a single PDF? `[Y/n]`
   - **Q2:** Do you need the second page (instructions)? `[y/N]`
   - **Q3:** Save both pages together or in separate combined files? `[1/2]`

---

#### Option B: Direct CLI Command (Using Report File)
```bash
midasdownloader download -f report_sample.xls -u "https://portal.university.example.edu/entrance/report/prints?entranceid={student_id}&levelid=3&facultyid=1&programid=30&status=&orgid=undefined&academicbatch=&verified=&isverified=&examcenterid=Y&fromdate=2026-05-27&todate=2026-08-20" -o out/BIT_Batch_2083
```

---

#### Option C: Combine an Existing Folder of PDFs
```bash
midasdownloader combine out/2026-08-20_12-41-12
```

---

## 🛠 CLI Options Reference

```text
Usage: midasdownloader download [OPTIONS]

Options:
  -f, --file PATH         Path to XLS, CSV, or TXT file (e.g. report_sample.xls)
  -i, --id TEXT           Single, multiple, or comma-separated entrance IDs
  -r, --range TEXT        Range of numerical IDs (e.g. 41600-41650)
  -u, --url TEXT          URL template with {student_id} placeholder
  -c, --cookie TEXT       Session cookie value (overrides .env)
  --cookie-name TEXT      Cookie key name (default: ci_session)
  -o, --output-dir PATH   Output folder (e.g. out/BIT_Batch_2083 or default: out/YYYY-MM-DD_HH-MM-SS)
  -d, --delay FLOAT       Delay in seconds between requests (default: 0.4s)
  --force                 Re-download and overwrite existing admit cards
  --no-combine            Skip post-download PDF combination prompt
  --interactive           Run interactive guided wizard
  --help                  Show this message and exit.
```

---

## 📦 Publishing to PyPI

To publish a new version to [PyPI](https://pypi.org/):

```bash
# 1. Build sdist and wheel
uv build

# 2. Publish to PyPI
uv publish --token <your-pypi-api-token>
```

Or trigger the automated GitHub Actions workflow by publishing a release on GitHub.

---

## 🛡 Security & Best Practices

- **Never commit `.env`:** The `.env` file contains your active login cookie and is ignored by `.gitignore`.
- **Session Expiration:** If downloads fail with `Authentication failed`, your session cookie in Chrome has expired. Simply log in again on Chrome and copy the refreshed `ci_session` value.
- **Server Courtesy:** The default delay between downloads is `0.4s` to ensure reliable downloads without triggering rate-limits.

---

## 📄 License

[MIT](LICENSE) © [Ayush Bhattarai](https://github.com/aaxyat)

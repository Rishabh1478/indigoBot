# IndigoBot

IndigoBot is a Python automation script designed to fetch and download **GST Invoices** from [IndiGo Airlines](https://book.goindigo.in/) using either **PNR** or **Invoice Number** along with the registered email. The invoices are processed in **batches** and saved as **PDF files**.

---

## 🚀 Features

- Fetch invoices by **PNR** or **Invoice Number**
- Batch processing with configurable **thread pool size** and **time interval**
- Automatic **HTML → PDF conversion** using `wkhtmltopdf`
- Logging of all activities into `indigo_bot.log`
- Error handling with retries and batch isolation
- CSV-based input for bulk invoice fetching
- Uses **Cloudscraper** to bypass Cloudflare protections

---

## 📂 Project Structure

```
.
├── indigo_bot.py           # Main script
├── replace_html_content.py # Custom helper for cleaning HTML response
├── indigo.csv              # Input file (PNR/Invoice + Email)
├── PDFs/                   # Saved invoices as PDFs
├── temp/                   # Temporary HTML files
└── indigo_bot.log          # Log file
```

---

## 📋 Requirements

- Python **3.8+**
- [wkhtmltopdf](https://wkhtmltopdf.org/) installed and accessible in:
  ```
  wkhtmltox/bin/wkhtmltopdf.exe
  ```
- Required Python packages (see below)

---

## 📦 Installation

1. Clone the repository or copy the script files.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` should include:

```
requests
pdfkit
pandas
beautifulsoup4
cloudscraper
```

3. Ensure `wkhtmltopdf` is installed and its path is correctly set in the script.

---

## 📝 Input File Format (`indigo.csv`)

The script expects a **CSV file** named `indigo.csv` with the following headers:

- If searching by **PNR**:
  ```
  PNR,EMAIL
  ABC123,john@example.com
  XYZ456,jane@example.com
  ```

- If searching by **Invoice Number**:
  ```
  INVOICE,EMAIL
  1234567890,john@example.com
  9876543210,jane@example.com
  ```

---

## ▶️ Usage

Run the script:

```bash
python indigo_bot.py
```

You will be prompted to provide:

1. **Batch size** → Number of PNR/Invoices to process at once  
2. **Time interval** → Delay (in seconds) between batches  
3. **Search Mode** →  
   - `1` → Search by **PNR**  
   - `2` → Search by **Invoice Number**

---

## 📄 Output

- Invoices are saved as **PDF files** inside the `PDFs/` folder.  
- Temporary HTML files are stored in the `temp/` folder.  
- Execution logs are written to `indigo_bot.log`.  

Example:

```
PDFs/
├── 1234567890.pdf
├── 9876543210.pdf
```

---

## ⚠️ Notes

- Make sure `indigo.csv` exists in the current directory.  
- Incorrect or missing inputs will cause the script to exit.  
- Ensure you have permission to access the invoices (valid email + PNR/Invoice Number).  
- This tool is for **personal/educational use only**.

---

## 🛠️ Logging & Debugging

- All activities are logged in `indigo_bot.log`.  
- Errors during invoice fetching or PDF generation are also logged.  

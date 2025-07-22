import os
import sys
import time
import logging
import requests
import pdfkit
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Literal
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed
from cloudscraper import create_scraper
from replace_html_content import replace_content

logging.basicConfig(
    filename='indigo_bot.log',
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    filemode='a'
)

def chunks(data_dict, size):
    it = iter(data_dict.items())
    for _ in range(0, len(data_dict), size):
        yield dict(islice(it, size))

def get_base_path():
    """Get base path depending on execution context (PyInstaller or script)"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

class IndigoBot:
    def __init__(self):
        self.soup_maker = lambda text: BeautifulSoup(text, 'html.parser')

        wkhtmltopdf_path = os.path.join(get_base_path(), "wkhtmltox", "bin", "wkhtmltopdf.exe")
        self.pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

        if not os.path.isfile("indigo.csv"):
            print("❌ indigo.csv not found in current directory.")
            exit(1)
        try:
            self.number_of_invoices_at_once = int(input("How many PNR/Invoice Numbers to process at once: "))
            self.time_interval = int(input("Time Interval (in Seconds): "))
            print("Enter Choice:\n1)Search By PNR\n2)Search By Invoice Number")
            type_choice: Literal[1, 2] = int(input(">>"))
            self.mode = "PNR" if type_choice == 1 else "INVOICE"
        except Exception as e:
            print("❌ Invalid input.")
            logging.exception("Input failure:", exc_info=e)
            sys.exit(1)

    def execute(self):
        self._create_session()
        data = self.read_csv()
        batched = list(chunks(data, self.number_of_invoices_at_once))

        print(f"\n🚀 Running {len(batched)} batches with up to {self.number_of_invoices_at_once} threads\n")
        with ThreadPoolExecutor(max_workers=self.number_of_invoices_at_once) as executor:
            futures = []
            for i, batch in enumerate(batched, 1):
                futures.append(executor.submit(self.process_batch, batch, self.mode, i))
                time.sleep(self.time_interval)

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()
                    print(f"✅ Finished batch {i}/{len(futures)}")
                except Exception as e:
                    logging.exception(f"❌ Error in batch {i}: {e}")
                    print(f"❌ Batch {i} failed: {e}")

    def process_batch(self, batch: dict, mode: str, batch_index: int):
        start = time.time()
        logging.info(f"🚀 Batch #{batch_index} started with {len(batch)} items.")

        for key, email in batch.items():
            try:
                if mode == "PNR":
                    invoices = self.fetch_all_invoice_number_for_a_datum(email, pnr=key)
                else:
                    invoices = self.fetch_all_invoice_number_for_a_datum(email, invoice_number=key)

                for invoice in invoices:
                    try:
                        self.make_data_fetch_request(email, invoice)
                        logging.info(f"[Batch {batch_index}] ✅ Processed invoice: {invoice}")
                    except Exception as invoice_err:
                        logging.exception(f"[Batch {batch_index}] ❌ Error with invoice {invoice}: {invoice_err}")
            except Exception as e:
                logging.exception(f"[Batch {batch_index}] ❌ Fetch error for {key}: {e}")

        duration = round(time.time() - start, 2)
        logging.info(f"✅ Batch #{batch_index} completed in {duration}s.")

    def fetch_all_invoice_number_for_a_datum(self, email: str, invoice_number=None, pnr=None):
        url = "https://book.goindigo.in/Booking/GSTInvoiceDetails"
        headers = {
            "Host": "book.goindigo.in",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Accept-Language": "en-GB,en;q=0.9",
            "Origin": "https://book.goindigo.in",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://book.goindigo.in/",
            "Accept-Encoding": "gzip, deflate, br",
            "Priority": "u=0, i",
            "Connection": "keep-alive"
        }
        data = {
            "indigoGSTDetails.IsIndigoSkin": "true",
            "indigoGSTDetails.PNR": pnr if pnr else "",
            "indigoGSTDetails.CustEmail": email if pnr else "",
            "indigoGSTDetails.InvoiceNumber": invoice_number if invoice_number else "",
            "indigoGSTDetails.InvoiceEmail": email if invoice_number else "",
            "GstRetrieve": "Retrieve"
        }
        response = requests.post(url, headers=headers, data=data)
        soup = self.soup_maker(response.text)
        invoice_links = soup.find_all("a", {"id": "PrintInvoice"})
        return [link.get("invoice-number") for link in invoice_links]

    def make_data_fetch_request(self, email, invoice_number):
        model_content1 = '<h4 class="modal-title">'
        model_content2 = 'Click OK to continue your session'
        model_content3 = '<button class="btntimer buttonGlbl"'
        model_content4 = 'id="closeTimeOut">OK</button>'

        url = "https://book.goindigo.in/Booking/GSTInvoice"
        headers = {
            "Host": "book.goindigo.in",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Accept-Language": "en-GB,en;q=0.9",
            "Origin": "https://book.goindigo.in",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://book.goindigo.in/",
            "Accept-Encoding": "gzip, deflate, br",
            "Priority": "u=0, i",
            "Connection": "keep-alive"
        }
        data = {
            "__RequestVerificationToken": "dummy",
            "IndigoGSTInvoice.InvoiceNumber": str(invoice_number),
            "IndigoGSTInvoice.IsPrint": "false",
            "IndigoGSTInvoice.GSTEmail": str(email),
            "IndigoGSTInvoice.isExempted": "",
            "IndigoGSTInvoice.ExemptedMsg": ""
        }

        response = requests.post(url, headers=headers, data=data)
        html_content = replace_content(response, model_content1, model_content2, model_content3, model_content4)

        html_content = html_content.replace('Your session is about to expire in', '').replace('''type="button" aria-hidden="true" data-dismiss="modal" onclick="javascript: window.location.href = domainurl">Cancel''', '').replace('type="button" aria-hidden="true"', '')
        index = html_content.find('<div class="modal fade" id="popup_login"')
        final_content = html_content[:index] if index != -1 else html_content

        os.makedirs("temp", exist_ok=True)
        html_path = os.path.join("temp", f"{invoice_number}.html")
        with open(html_path, "w", encoding="utf-8") as file:
            file.write(final_content)

        os.makedirs("PDFs", exist_ok=True)
        pdf_path = os.path.join("PDFs", f"{invoice_number}.pdf")
        pdfkit.from_file(html_path, pdf_path, configuration=self.pdfkit_config)
        logging.info(f"✅ PDF created: {pdf_path}")

    def _create_session(self):
        self.session = requests.Session()
        self.session = create_scraper(self.session)
        try:
            headers = {
            "Host": "book.goindigo.in",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Accept-Language": "en-GB,en;q=0.9",
            "Origin": "https://book.goindigo.in",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://book.goindigo.in/",
            "Accept-Encoding": "gzip, deflate, br",
            "Priority": "u=0, i",
            "Connection": "keep-alive"
        }
            r = self.session.get("https://www.goindigo.in/view-gst-invoice.html", headers=headers)
            logging.info(f"[Session] Indigo site status: {r.status_code}")
        except Exception as e:
            logging.exception("⛔ Session initialization failed.", exc_info=True)

    def read_csv(self):
        df = pd.read_csv("indigo.csv")
        if self.mode == "PNR":
            return {row["PNR"]: row["EMAIL"] for _, row in df.iterrows()}
        elif self.mode == "INVOICE":
            return {row["INVOICE"]: row["EMAIL"] for _, row in df.iterrows()}

if __name__ == "__main__":
    try:
        run = IndigoBot()
        run.execute()
    except KeyboardInterrupt:
        print("🛑 Interrupted by user.")
    except Exception as e:
        logging.exception(f"🚨 Script crashed: {e}")

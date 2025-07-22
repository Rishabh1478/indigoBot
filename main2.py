import os
from pprint import pprint
from typing import Literal
import pandas as pd
import requests
from cloudscraper import create_scraper
from pathlib import Path
from bs4 import BeautifulSoup
import time
import pdfkit
import logging
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed
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

class IndigoBot:
    def __init__(self):
        self.soup_maker = lambda response_text: BeautifulSoup(response_text, 'html.parser')
        try:
            if not os.path.isfile(os.path.join(os.getcwd(), "indigo.csv")):
                print("No 'indigo.csv' file detected, please add the file in the current directory.")
                exit(0)
            self.number_of_invoices_at_once = int(input("How many PNR/Invoice Numbers to process at once: "))
            self.time_interval = int(input("Time Interval (in Seconds): "))
            print("Enter Choice:\n1)Search By PNR\n2)Search By Invoice Number")
            type_choice: Literal[1, 2] = int(input(">>"))
            self.mode = "PNR" if type_choice == 1 else "INVOICE"
        except (ValueError, TypeError):
            print("Wrong value input, please check!!")
            exit(1)

    def execute(self):
        self._create_session()
        details_dict = self.read_csv()
        batched_dicts = list(chunks(details_dict, self.number_of_invoices_at_once))

        logging.info(f"Total batches: {len(batched_dicts)} | Max workers: {self.number_of_invoices_at_once}")
        print(f"\n🚀 Running {len(batched_dicts)} batches with up to {self.number_of_invoices_at_once} in parallel...\n")

        with ThreadPoolExecutor(max_workers=self.number_of_invoices_at_once) as executor:
            futures = []
            for i, batch in enumerate(batched_dicts, 1):
                future = executor.submit(self.process_batch, batch, self.mode, i)
                futures.append(future)
                time.sleep(self.time_interval)

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()
                    print(f"✅ Finished batch {i}/{len(futures)}")
                except Exception as e:
                    logging.exception(f"❌ Error in executing batch #{i}: {str(e)}")
                    print(f"❌ Error in batch {i}: {e}")

    def process_batch(self, batch: dict, mode: str, batch_index: int):
        start = time.time()
        logging.info(f"🚀 Starting Batch #{batch_index} with {len(batch)} items")
        try:
            for key, email in batch.items():
                try:
                    if mode == "PNR":
                        invoice_numbers = self.fetch_all_invoice_number_for_a_datum(email, pnr=key)
                    else:
                        invoice_numbers = self.fetch_all_invoice_number_for_a_datum(email, invoice_number=key)

                    logging.info(f"[Batch {batch_index}] {key} - Invoices Found: {invoice_numbers}")

                    for invoice in invoice_numbers:
                        try:
                            self.make_data_fetch_request(email, invoice)
                            logging.info(f"[Batch {batch_index}] Processed invoice: {invoice}")
                        except Exception as inv_error:
                            logging.exception(f"[Batch {batch_index}] ❌ Error processing invoice {invoice}: {inv_error}")

                except Exception as item_error:
                    logging.exception(f"[Batch {batch_index}] ❌ Error fetching invoices for: {key} | {item_error}")

        except Exception as e:
            logging.exception(f"[Batch {batch_index}] ❌ Unhandled batch error: {e}")
        finally:
            end = time.time()
            duration = round(end - start, 2)
            logging.info(f"✅ Completed Batch #{batch_index} in {duration} seconds")

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
        links = soup.find_all('a', {'id': 'PrintInvoice'})
        return [tag.get('invoice-number') for tag in links]

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
            "__RequestVerificationToken": "dummy",  # Likely not needed
            "IndigoGSTInvoice.InvoiceNumber": str(invoice_number),
            "IndigoGSTInvoice.IsPrint": "false",
            "IndigoGSTInvoice.GSTEmail": str(email),
            "IndigoGSTInvoice.isExempted": "",
            "IndigoGSTInvoice.ExemptedMsg": ""
        }

        response = requests.post(url, headers=headers, data=data)
        html_content = replace_content(response, model_content1, model_content2, model_content3, model_content4)

        html_content = html_content.replace('Your session is about to expire in', '').replace('''type="button" aria-hidden="true" data-dismiss="modal" onclick="javascript: window.location.href = domainurl">Cancel''', '').replace('type="button" aria-hidden="true"', '')
        # Remove unnecessary modal popup
        index = html_content.find('<div class="modal fade" id="popup_login"')
        final_content = html_content[:index] if index != -1 else html_content

        # Save HTML
        os.makedirs("temp", exist_ok=True)
        html_path = os.path.join("temp", f"{invoice_number}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(final_content)

        # Convert to PDF
        os.makedirs("PDFs", exist_ok=True)
        pdf_path = os.path.join("PDFs", f"{invoice_number}.pdf")
        pdfkit.from_file(html_path, pdf_path)
        logging.info(f"✅ PDF saved: {pdf_path}")

    def _create_session(self):
        self.session = requests.Session()
        self.session = create_scraper(self.session)
        url = "https://www.goindigo.in/view-gst-invoice.html"

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

        r = self.session.get(url, headers=headers)
        logging.info(f"[Session Init] Indigo invoice page status: {r.status_code}")

    def read_csv(self):
        df = pd.read_csv('indigo.csv')
        if self.mode == "PNR":
            logging.info("Processing mode: PNR")
            return {row['PNR']: row['EMAIL'] for _, row in df.iterrows()}
        elif self.mode == "INVOICE":
            logging.info("Processing mode: INVOICE")
            return {row['INVOICE']: row['EMAIL'] for _, row in df.iterrows()}

if __name__ == "__main__":
    try:
        run = IndigoBot()
        run.execute()
    except KeyboardInterrupt:
        print("👋 Interrupted by user.")
    except Exception as e:
        logging.exception(f"❌ Unhandled exception: {e}")

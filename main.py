import os
from pprint import pprint
from typing import Literal
import pandas as pd
import requests
from cloudscraper import create_scraper
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from replace_html_content import replace_content
import time
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    filename='indigo_bot.log',
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    filemode='a'
)

def chunks(data_dict, size):
    """Yield successive chunks (as dictionaries) from a dictionary."""
    it = iter(data_dict.items())
    for _ in range(0, len(data_dict), size):
        yield dict(islice(it, size))

class IndigoBot:
    def __init__(self):
        self.soup_maker = lambda response_text: BeautifulSoup(response_text, 'html.parser')
        try:
            if not os.path.isfile(os.path.join(os.getcwd(), "indigo.csv")):
                print("No 'indigo.csv' file detected, please add file in current working directory")
                exit(0)
            self.number_of_invoices_at_once: int = int(input("How many PNR/Invoice Numbers numbers to process at once: "))
            self.time_interval: int = int(input("Time Interval (in Seconds): "))
            print("Enter Choice:\n1)Search By PNR\n2)Search By Invoice Number")
            type_choice: Literal[1, 2] = int(input(">>"))
            if type_choice == 1:
                self.mode = "PNR"
            elif type_choice == 2:
                self.mode = "INVOICE"
            self.get_playwright_page()

        except TypeError:
            print("Wrong value input, please check!!")
        except ValueError:
            print("Wrong value input, please check!!")

    def execute(self):
        self._create_session()
        details_dict = self.read_csv()
        batched_dicts = list(chunks(details_dict, self.number_of_invoices_at_once))

        max_workers = self.number_of_invoices_at_once
        logging.info(f"Total batches: {len(batched_dicts)} | Max workers: {max_workers}")

        print(f"\n🚀 Running {len(batched_dicts)} batches with up to {max_workers} in parallel...\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, batch in enumerate(batched_dicts, 1):
                logging.info(f"Submitting batch {i} for execution")
                future = executor.submit(self.process_batch, batch, self.mode, i)
                futures.append(future)
                time.sleep(self.time_interval)  # delay between launching batches

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()
                    print(f"✅ Finished batch {i}/{len(futures)}")
                except Exception as e:
                    logging.exception(f"❌ Error in executing batch #{i}: {str(e)}")
                    print(f"❌ Error in batch {i}: {e}")

    def get_playwright_page(self, headless: bool = True):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        return playwright, browser, context, page

    def process_batch(self, batch: dict, mode: str, batch_index: int):
        start = time.time()
        logging.info(f"🚀 Starting Batch #{batch_index} with {len(batch)} items")
        playwright, browser, context, page = self.get_playwright_page()

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
                            self.make_data_fetch_request(email, invoice, page)
                            logging.info(f"[Batch {batch_index}] Processed invoice: {invoice}")
                        except Exception as inv_error:
                            logging.exception(f"[Batch {batch_index}] ❌ Error processing invoice {invoice}: {inv_error}")

                except Exception as item_error:
                    logging.exception(f"[Batch {batch_index}] ❌ Error fetching invoices for: {key} | {item_error}")

        except Exception as e:
            logging.exception(f"[Batch {batch_index}] ❌ Unhandled batch error: {e}")

        finally:
            browser.close()
            playwright.stop()
            end = time.time()
            duration = round(end - start, 2)
            logging.info(f"✅ Completed Batch #{batch_index} in {duration} seconds")

    def fetch_all_invoice_number_for_a_datum(self, email: str, invoice_number=None, pnr = None):
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
            "indigoGSTDetails.PNR": pnr if pnr != None else "",
            "indigoGSTDetails.CustEmail": email if pnr != None else "",
            "indigoGSTDetails.InvoiceNumber": invoice_number if invoice_number != None else "",
            "indigoGSTDetails.InvoiceEmail": email if invoice_number != None else "",
            "GstRetrieve": "Retrieve"
        }

        # Make the POST request
        response = requests.post(url, headers=headers, data=data)
        open('2.html', "w").write(response.text)
        soup = self.soup_maker(response.text)
        all_invoice_numbers = soup.find_all('a', {'id': 'PrintInvoice'})
        all_invoice_numbers = [invoiceNum.get('invoice-number') for invoiceNum in all_invoice_numbers]
        return all_invoice_numbers



    def make_data_fetch_request(self, email, invoice_number, page):
        model_content = '<h4 class=\"modal-title\">Your session is about to expire in <span id=\"timer\"></span></h4>'
        model_content2 = 'Click OK to continue your session <input type=\"hidden\" id=\"hdncount\" value=\"120\" />'
        model_content3 = '<button class=\"btntimer buttonGlbl\" type=\"button\" aria-hidden=\"true\" data-dismiss=\"modal\" onclick=\"javascript: window.location.href = domainurl\">Cancel</button>'
        model_content4 = '<button class=\"btntimer buttonGlbl\" type=\"button\" aria-hidden=\"true\" id=\"closeTimeOut\">OK</button>'

        url = "https://book.goindigo.in/Booking/GSTInvoice"

        headers = {
            "Host": "book.goindigo.in",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Accept-Language": "en-GB,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Origin": "https://book.goindigo.in",
            "Content-Type": "application/x-www-form-urlencoded",
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
            "__RequestVerificationToken": "asda",
            "IndigoGSTInvoice.InvoiceNumber": str(invoice_number),
            "IndigoGSTInvoice.IsPrint": "false",
            "IndigoGSTInvoice.GSTEmail": str(email),
            "IndigoGSTInvoice.isExempted": "",
            "IndigoGSTInvoice.ExemptedMsg": ""
        }
        
        # exit()
        response = requests.post(url, headers=headers, data=data)

        html_content = replace_content(response, model_content, model_content2, model_content3, model_content4)
        index = html_content.index('<div class=\"modal fade\" id=\"popup_login\" role=\"dialog\" aria-labelledby=\"myModalLabel\" aria-hidden=\"true\">')
        final_content = html_content[:index]
        file_url = lambda path: Path(path).absolute().as_uri()
        os.makedirs(os.path.join("temp"), exist_ok=True)
        open(os.path.join("temp", f'{invoice_number}.html'), 'w').write(final_content)
        page.goto(file_url(os.path.join("temp", f'{invoice_number}.html')))
        os.makedirs(os.path.join("PDFs"),exist_ok=True)
        page.pdf(path=os.path.join("PDFs", f"{invoice_number}.pdf"))
                



    def _create_session(self):
        self.session = requests.Session()
        self.sesison = create_scraper(self.session)
        URL = "https://www.goindigo.in/view-gst-invoice.html"


        headers = {
        "Accept": "*/*",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Origin": "https://www.goindigo.in",
        "Referer": "https://www.goindigo.in/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        }
        r1 = self.session.get(URL, headers=headers)
        print(r1.status_code)

    def read_csv(self):
        df = pd.read_csv(os.path.join(os.getcwd(), 'indigo.csv'))
        if self.mode == "PNR":
            print("processing pnr")
            PNRs = df['PNR'].tolist()
            EMAIL = df["EMAIL"].tolist()
            final_dict = {pnr: email for pnr, email in zip(PNRs, EMAIL)}
        elif self.mode == "INVOICE":
            print("processing Invoice")
            INVOICE_NUMS = df['INVOICE'].tolist()
            EMAIL = df["EMAIL"].tolist()
            final_dict = {invoice: email for invoice, email in zip(INVOICE_NUMS, EMAIL)}
        return final_dict
    
if __name__ == "__main__":
    run = IndigoBot()
    run.execute()
    
    
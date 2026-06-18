from playwright.async_api import async_playwright
import requests
from config import PROGRESS_FILE, OUTPUT_DIR, OUTPUT_FILE, MAX_RETRIES, RETRY_DELAY, TOTAL_PAGES, BATCH_SIZE, CONCURRENCY
from dotenv import load_dotenv
import asyncio
import json
import os
import csv
import time

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = os.getenv("BASE_URL")

def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram Message Error", e)

def send_telegram_file(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID}, files={"document": f})
    except Exception as e:
        print("Telegram File Error", e)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_page":0, "last_link_index":-1, "batch_count":0}

def save_progress(page_num, link_index, batch_count):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_page": page_num,
                "last_link_index": link_index,
                "batch_count": batch_count
            }, f
        )

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def write_csv_batch(batch_data: list[dict], batch_num: int)-> str:
    rows = list(batch_data)
    all_cols = list(dict.fromkeys(col for row in rows for col in row.keys()))
    file_path = os.path.join(OUTPUT_DIR, f"Batch_{batch_num}.csv")
    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return file_path

def merged_batches():
    batch_files = sorted([
        os.path.join(OUTPUT_DIR, f)
        for f in os.listdir(OUTPUT_DIR)
        if f.startswith("Batch_") and f.endswith(".csv")
    ])

    if not batch_files:
        return
    
    all_cols = []
    for batch in batch_files:
        with open(batch, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for col in reader.fieldnames or []:
                if col not in all_cols:
                    all_cols.append(col)
    final_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(final_path, "w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        for batch in batch_files:
            with open(batch, "r", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    writer.writerow(row)
    for batch in batch_files:
        os.remove(batch)

    print(f"Final Output at {final_path}")


async def scrape_page_link(page, page_num):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await page.goto(
                f"{BASE_URL}/en/broker/egypt-best-properties-85?properties%5Bpage%5Bnumber%5D%5D={page_num}",
                wait_until = "domcontentloaded",
                timeout = 30000
            )
            await page.wait_for_timeout(5000)
            links = await page.locator("ul.styles_desktop_container__VYv4U li a").evaluate_all(
                "elements => elements.map(el => el.getAttribute('href'))"
            )
            return links
        except Exception as e:
            print(f"Page {page_num} attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"Skipping page {page_num} after {MAX_RETRIES} retries")
                return []


async def scrape_property_details(context, url, semaphore):
    async with semaphore:
        page = await context.new_page()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await page.goto(f"{BASE_URL}{url}", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
                property_data = {}
                property_data['title'] = page.locator('h1.styles_desktop_title__j0uNx').inner_text()
                property_data['price'] = int(page.locator('[data-testid="property-price-value"]').inner_text(timeout=5000).replace(',', ''))
                property_data['bedrooms'] = int(page.locator('[data-testid="property-attributes-bedrooms"]').inner_text().split(" ")[0])
                room_idx = page.locator('[data-testid="property-attributes-bedrooms"]').inner_text().find("Maid")
                if room_idx == -1:
                    property_data['has_maid_room'] = 'No'
                else:
                    property_data['has_maid_room'] = 'Yes'
                property_data['bathrooms'] = int(page.locator('[data-testid="property-attributes-bathrooms"]').inner_text().split(" ")[0])
                property_data['area sqm'] = int(page.locator('[data-testid="property-attributes-size"]').inner_text().split(" ")[0])
                property_data['title'] = page.locator('h1.styles_desktop_title__j0uNx').inner_text()
                property_data['property_type'] = page.locator('[data-testid="property-details-type"]').inner_text()
                property_data['available from'] = page.locator('[data-testid="property-details-rental-availability-date"]').inner_text()
                property_data['location'] = page.locator('#location p.styles-module_map__title__M2mBC').inner_text()
                
                property_data['amenities'] = page.locator('section#amenities .styles_text__IlyiW').all_inner_texts()
            except Exception as e:
                print(f"Property {url} attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Skipping Property {url} after {MAX_RETRIES} retries")
                    return None
            finally:
                pass

        await page.close()
        return property_data
    
async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    start_time = time.time()
    progress = load_progress()
    start_page = progress["last_page"] if progress["last_page"] > 0 else 1
    skip_links_before = progress["last_link_index"] + 1
    batch_count = progress["batch_count"]

    batch_data = []
    properties_counter = 0
    current_page = start_page
    current_chunck_index = 0

    is_resuming = progress["last_page"] > 0
    if is_resuming:
        send_telegram_message(
            f"Resuming scraping from page {start_page}, "
            f"link index {skip_links_before}, batch #{batch_count + 1}"
        )
    else:
        send_telegram_message("Scraping started")
    async with async_playwright() as p:
        try:
            for page_num in range(start_page, TOTAL_PAGES + 1):
                current_page = page_num
                print(f"Scraping page {page_num}/{TOTAL_PAGES}")
                
                list_browser = await p.chromium.launch(headless=False)
                list_context = await list_browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                list_page = await list_context.new_page()
                links = await scrape_page_link(list_page, page_num)
                await list_browser.close()

                for i in range(0, len(links), BATCH_SIZE):
                    current_chunck_index = i
                    if page_num == start_page and i < skip_links_before:
                        continue
                    chunck_links = links[i: i + BATCH_SIZE]
                    print(f"Processing batch of {len(chunck_links)} links concurrently...")

                    chunck_browser = await p.chromium.launch(headless=False)
                    chunck_context = await chunck_browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 720}
                    )
                    semaphore = asyncio.Semaphore(CONCURRENCY)
                    tasks = [
                        scrape_property_details(chunck_context, link, semaphore) 
                        for link in chunck_links
                    ]
                    res = await asyncio.gather(*tasks, return_exceptions=True)
                    await chunck_browser.close()

                    for result in res:
                        if isinstance(result, dict) and result is not None:
                            batch_data.append(result)
                            properties_counter += 1
                        elif isinstance(res, Exception):
                            print(f"Exception during gathering: {res}") 
                    
                    if batch_data:
                        batch_count += 1
                        file_path = write_csv_batch(batch_data, batch_count)
                        send_telegram_file(file_path)
                        print(f"Batch {batch_count} sent ({len(batch_data)} properties)")


                        save_progress(page_num, i + len(chunck_links) - 1, batch_count)
                        batch_data = []
            if batch_data:
                batch_count += 1
                file_path = write_csv_batch(batch_data, batch_count)
                send_telegram_file(file_path)
                print(f"Batch {batch_count} sent ({len(batch_data)} properties)")
            
            merged_batches()

            clear_progress()

            end_time = time.time()
            duration = end_time - start_time
            send_telegram_message(
                f"Scraping completed!\n"
                f"Properties scraped: {properties_counter}\n"
                f"Batches sent: {batch_count}\n"
                f"Duration: {duration:.2f}s\n"
                f"Final file: {OUTPUT_FILE}"
            )
        except Exception as e:

            if batch_data:
                batch_count += 1
                file_path = write_csv_batch(batch_data, batch_count)
                send_telegram_file(file_path)

            save_progress(current_page, current_chunck_index, batch_count)
            print(f"Saved progress at page {current_page}, chunk offset {current_chunck_index} before exit")

            send_telegram_message(
                f"Scraping crashed: {e}\nRun again to resume."
            )
            try:
                if 'chunk_browser' in locals() and chunck_browser:
                    await chunck_browser.close()
                if 'list_browser' in locals() and list_browser:
                    await list_browser.close()
            except Exception:
                pass
            raise     


if __name__ == "__main__":
    asyncio.run(main())

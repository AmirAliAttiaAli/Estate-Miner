from playwright.async_api import async_playwright, Error
import requests
from config import PROGRESS_FILE, OUTPUT_DIR, OUTPUT_FILE, MAX_RETRIES, RETRY_DELAY, TOTAL_PAGES, BATCH_SIZE, CONCURRENCY
from dotenv import load_dotenv
import asyncio
import json
import os
import csv
import time
import random

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = os.getenv("BASE_URL")
USER_DATA_DIR = os.path.join("output", "browser_profile")


def random_delay(min_seconds = 2, max_seconds = 5):
    return random.uniform(min_seconds, max_seconds)


async def apply_stealth(context):
    stealth_script = """
    () => {
        Object.defineProperty(navigator, 'webdriver', {get: () => false});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = parameters => 
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters);
    }
    """
    await context.add_init_script(stealth_script)


def is_context_closed_error(exc):
    return isinstance(exc, Error) and "Target page, context or browser has been closed" in str(exc)


async def create_context(p):
    return await p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process"
        ],
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720}
    )


def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram Message Error", e)

def send_telegram_file(file_path):
    if not file_path:
        return
    if not os.path.exists(file_path):
        print(f"Telegram File Error: file not found: {file_path}")
        return
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
    if not batch_data:
        return ""
    file_path = os.path.join(OUTPUT_DIR, f"Batch_{batch_num}.csv")
    all_cols = list(dict.fromkeys(col for row in batch_data for col in row.keys()))
    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(batch_data)
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
        target_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        property_data = {}


        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(random_delay(4,7))

                property_data['title'] = await page.locator('h1.styles_desktop_title__j0uNx').inner_text()

                price_text = await page.locator('[data-testid="property-price-value"]').inner_text(timeout=5000)
                property_data['price'] = int(''.join(ch for ch in price_text if ch.isdigit()))

                bedrooms_text = await page.locator('[data-testid="property-attributes-bedrooms"]').inner_text()
                bedrooms_number = ''.join(ch for ch in bedrooms_text if ch.isdigit())
                property_data['bedrooms'] = int(bedrooms_number) if bedrooms_number else None

                property_data["has_maid_room"] = "Yes" if "maid" in bedrooms_text.lower() else "No"
                
                bathroom_text = await page.locator('[data-testid="property-attributes-bathrooms"]').inner_text()
                bathroom_number = ''.join(ch for ch in bathroom_text if ch.isdigit())
                property_data['bathrooms'] = int(bathroom_number) if bathroom_number else None

                area_text = await page.locator('[data-testid="property-attributes-size"]').inner_text()
                area_number = ''.join(ch for ch in area_text if ch.isdigit())
                property_data['area sqm'] = int(area_number) if area_number else None

                property_data['property_type'] = await page.locator('[data-testid="property-details-type"]').inner_text()

                try:
                    property_data['available from'] = await page.locator('[data-testid="property-details-rental-availability-date"]').inner_text(timeout=2000)
                except:
                    property_data["available from"] = "N/A"

                property_data['location'] = await page.locator('#location p.styles-module_map__title__M2mBC').inner_text()
                
                amanities_list = await page.locator('section#amenities .styles_text__IlyiW').all_inner_texts()
                property_data['amenities'] = ", ".join(amanities_list)
                break
            except Exception as e:
                print(f"Property {url} attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Skipping Property {url} after {MAX_RETRIES} retries")
                    await page.close()
                    return None

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
    
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await create_context(p)
            await apply_stealth(context)

            for page_num in range(start_page, TOTAL_PAGES + 1):
                current_page = page_num
                print(f"Scraping page {page_num}/{TOTAL_PAGES}")

                list_page = await context.new_page()
                links = await scrape_page_link(list_page, page_num)
                await list_page.close()

                for i in range(0, len(links), BATCH_SIZE):
                    current_chunck_index = i
                    if page_num == start_page and i < skip_links_before:
                        continue

                    chunck_links = links[i: i + BATCH_SIZE]
                    print(f"Processing batch of {len(chunck_links)} links with concurrency={CONCURRENCY}...")

                    batch_retry = 0
                    batch_results = []
                    while batch_retry < 2:
                        semaphore = asyncio.Semaphore(CONCURRENCY)
                        tasks = [
                            scrape_property_details(context, link, semaphore)
                            for link in chunck_links
                        ]
                        res = await asyncio.gather(*tasks, return_exceptions=True)

                        if any(is_context_closed_error(result) for result in res if isinstance(result, Exception)):
                            batch_retry += 1
                            print("Context was closed during the batch. Recreating browser context and retrying batch...")
                            try:
                                await context.close()
                            except Exception:
                                pass
                            context = await create_context(p)
                            await apply_stealth(context)
                            batch_results = []
                            continue

                        for result in res:
                            if isinstance(result, dict) and result is not None:
                                batch_results.append(result)
                                properties_counter += 1
                            elif isinstance(result, Exception):
                                print(f"Exception during gathering: {result}")
                        break

                    if batch_results:
                        batch_count += 1
                        file_path = write_csv_batch(batch_results, batch_count)
                        send_telegram_file(file_path)
                        print(f"Batch {batch_count} sent ({len(batch_results)} properties)")

                        save_progress(page_num, i + len(chunck_links) - 1, batch_count)
                        batch_results = []

                await asyncio.sleep(random_delay(2, 4))

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
        raise
    

if __name__ == "__main__":
    asyncio.run(main())

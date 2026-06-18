from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import os
load_dotenv()
page_num = 1
BASE_URL = os.getenv("BASE_URL")
LISTING_PATH = os.getenv("LISTING_PATH")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = context.new_page()
    page.goto(f"{BASE_URL}/en/broker/egypt-best-properties-85?properties%5Bpage%5Bnumber%5D%5D={page_num}")
    links = page.locator("ul.styles_desktop_container__VYv4U li a").evaluate_all(
        "elements => elements.map(el => el.getAttribute('href'))"
    )
    # print(links)
    page.goto(f"{links[0]}", wait_until='domcontentloaded', timeout=60000)
    property_data = {}
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
    
    print(property_data)
    # page.wait_for_timeout(5000)
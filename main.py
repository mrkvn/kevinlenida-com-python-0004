import json
import os
import time

from curl_cffi import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from selectolax.parser import HTMLParser


def load_page_and_scroll(url, selector, scrollable_selectors):
    def is_element_in_viewport(selector):
        return page.evaluate(
            """
            (selector) => {
                const element = document.querySelector(selector);
                if (!element) return false;
                const rect = element.getBoundingClientRect();
                return (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                );
            }
            """,
            selector,
        )

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        stealth_sync(page)
        page.goto(url)

        scrollable_selector = None
        for sel in scrollable_selectors:
            if page.query_selector(sel):
                scrollable_selector = sel
                break

        start_time = time.time()
        while not is_element_in_viewport(selector):
            page.evaluate(
                """
                    (scrollableSelector) => {{
                        const scrollableElement = document.querySelector(scrollableSelector);
                        if (scrollableElement) {{
                            scrollableElement.scrollBy(0, window.innerHeight);
                        }}
                    }}
                    """,
                scrollable_selector,
            )
            end_time = time.time()
            elapsed_time = end_time - start_time
            if elapsed_time > 30:  # more than number of seconds
                return None
            page.wait_for_timeout(500)

        page.wait_for_selector(selector)
        element_text = page.inner_text(selector)

        # Close the browser
        browser.close()

        return element_text.strip()


def try_requests(url, num_tries=10):
    timeout = 10  # seconds
    to_impersonate = ["chrome", "safari", "safari_ios"]
    index = 0
    for _ in range(num_tries):
        response = requests.get(url, impersonate=to_impersonate[index])
        tree = HTMLParser(response.text)
        title = tree.css_first("title")
        title_text = title.text()
        if "denied" in title_text.lower():
            if index == len(to_impersonate) - 1:
                index = 0
            else:
                index += 1
            time.sleep(timeout)
            print(f"Access denied. Waiting {timeout} seconds before trying again.")
        else:
            return response
    return None


def save_to_json(file_path, data):
    with open(file_path, "w") as file:
        json.dump(data, file, indent=2)


def main():
    json_file_path = "zillow.json"
    if os.path.exists(json_file_path):
        with open(json_file_path) as f:
            scraped_data = json.load(f)
    else:
        scraped_data = []
    url = "INSERT_URL_HERE"
    response = try_requests(url)
    if response is None:
        print("Could not get data from URL. Try again later.")
        return
    tree = HTMLParser(response.text)
    script = tree.css_first("script#__NEXT_DATA__")
    script_dict = json.loads(script.text())
    real_properties = script_dict["props"]["pageProps"]["searchPageState"]["cat1"]["searchResults"]["listResults"]
    for property in real_properties:
        address = property["address"]
        street = property["addressStreet"]
        city = property["addressCity"]
        state = property["addressState"]
        zip_code = property["addressZipcode"]
        price = property["unformattedPrice"] if "unformattedPrice" in property else None
        phone_number = None

        url = (
            property["detailUrl"]
            if property["detailUrl"].startswith("http")
            else f"https://www.zillow.com{property['detailUrl']}"
        )
        print(f"Processing: {url}")
        response = try_requests(url)
        if response is not None:
            tree = HTMLParser(response.text)
            script = tree.css_first("script#__NEXT_DATA__")
            script_dict = json.loads(script.text())
            try:
                phone_number = script_dict["props"]["pageProps"]["componentProps"]["initialReduxState"]["gdp"][
                    "building"
                ]["buildingPhoneNumber"]
            except KeyError as e:
                # print(f"ERROR: {e}")
                phone_selector = "li.ds-listing-agent-info-text"
                scrollable_selectors = ["div.data-view-container", "div.layout-container-desktop"]
                num_tries = 5
                for _ in range(num_tries):
                    phone_number = load_page_and_scroll(url, phone_selector, scrollable_selectors)
                    if phone_number is not None:
                        break
                    print(f"Cannot get phone number for: {url}. Retrying...")

        data = {
            "address": address,
            "street": street,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "price": price,
            "url": url,
            "phone_number": phone_number,
        }
        scraped_data.append(data)
        save_to_json(json_file_path, scraped_data)

        time.sleep(2)


if __name__ == "__main__":
    main()

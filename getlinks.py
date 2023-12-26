import asyncio
from playwright.async_api import async_playwright

async def fetch_links(url, browser):
    page = await browser.new_page()
    await page.goto(url)
    links = await page.query_selector_all('a')
    valid_links = []
    for link in links:
        href = await link.get_attribute('href')
        if href and (href.startswith('http') or href.startswith('https')):
            valid_links.append(href)
    await page.close()
    return valid_links

async def fetch_html(url, browser):
    page = await browser.new_page()
    await page.goto(url)
    html_content = await page.content()
    await page.close()
    return html_content

async def main():
    target_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770'  # Replace with your target URL
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        links = await fetch_links(target_url, browser)

        for link in links:
            try:
                html_content = await fetch_html(link, browser)
                print(f"HTML content for {link}:\n{html_content}\n")
            except Exception as e:
                print(f"Error fetching {link}: {e}")
            break  # Remove this 'break' if you want to process all links

        await browser.close()

asyncio.run(main())

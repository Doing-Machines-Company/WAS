from bs4 import BeautifulSoup


def extract_and_format_item_options(row):
    options = row.find('dl', class_='item-options')
    if not options:
        return ""
    option_text = '; '.join(f"{dt.get_text(strip=True)}: {dd.get_text(strip=True)}" for dt, dd in
                            zip(options.find_all('dt'), options.find_all('dd')))
    return f" [{option_text}]"


def extract_and_format_table_rows(table):
    items = []
    for tbody in table.find_all('tbody'):
        for row in tbody.find_all('tr'):
            item = {}
            for td in row.find_all('td'):
                key = td.get('data-th')
                if key == 'Product Name':
                    # Extract only the product name, excluding options
                    product_name = td.find('strong', class_='product name product-item-name').get_text(strip=True)
                    item[key] = product_name + extract_and_format_item_options(row)
                else:
                    value = td.get_text(strip=True)
                    item[key] = value
            items.append(item)
    return items

def extract_and_format_footer(footer):
    footer_details = {}
    for row in footer.find_all('tr'):
        key = row.find('th').get_text(strip=True)
        value = row.find('td').get_text(strip=True)
        footer_details[key] = value
    return footer_details


def extract_non_table_data(soup):
    order_number = soup.find('span', {'data-ui-id': 'page-title-wrapper'}).get_text(strip=True)
    order_status = soup.find('span', class_='order-status').get_text(strip=True)
    order_date = soup.find('div', class_='order-date').get_text(strip=True).replace('Order Date:', '').strip()

    shipping_address = soup.find('div', class_='box box-order-shipping-address').get_text(separator='\n', strip=True)
    billing_address = soup.find('div', class_='box box-order-billing-address').get_text(separator='\n', strip=True)

    return order_number, order_status, order_date, shipping_address, billing_address


def extract_order_page(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')

    table = soup.find('table', {'summary': 'Items Ordered'})
    items_ordered = extract_and_format_table_rows(table)
    footer = table.find('tfoot')
    footer_details = extract_and_format_footer(footer)

    order_number, order_status, order_date, shipping_address, billing_address = extract_non_table_data(soup)

    items_str = '\n'.join([
                              f"{item['Product Name']} - SKU: {item['SKU']}, Price: {item['Price']}, Qty: {item['Qty']}, Subtotal: {item['Subtotal']}"
                              for item in items_ordered])
    footer_str = '\n'.join([f"{key}: {value}" for key, value in footer_details.items()])

    non_table_str = f"Order Number: {order_number}\nStatus: {order_status}\nDate: {order_date}\n\n\n{shipping_address}\n\n\n{billing_address}\n"

    return non_table_str + "\n" + items_str + "\n\n" + footer_str
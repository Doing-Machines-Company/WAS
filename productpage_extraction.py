from bs4 import BeautifulSoup

def extract_product_page(html_content):
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the product information div
    product_info_div = soup.find('div', class_='product attribute description')

    # If the div is not found, return a message
    if not product_info_div:
        return "Product information not found."

    # Initialize a string to hold all formatted information
    formatted_info = ''

    # Extracting product details
    product_description = product_info_div.find('div', id='shortDescription')
    product_details_table = product_info_div.find('table', id='productDetails_detailBullets_sections1')

    # Format the product description
    if product_description:
        description_items = product_description.find_all('span', class_='a-list-item')
        formatted_info += "Product Description:\n"
        formatted_info += '\n'.join(f"- {item.get_text(strip=True)}" for item in description_items)
        formatted_info += '\n\n'  # Add some space between sections

    # Format the product details
    if product_details_table:
        formatted_info += "Product Details:\n"
        rows = product_details_table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            if len(cells) == 2:
                key = ' '.join(cells[0].get_text(strip=True).split())
                value = ' '.join(cells[1].get_text(strip=True).split())
                formatted_info += f"{key}: {value}\n"

    return formatted_info

# Example usage:
# html_content = [Your complete HTML page content here]
# product_info = extract_product_page(html_content)
# print(product_info)

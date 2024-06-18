from playwright.sync_api import sync_playwright

# User information dictionary
user_info = {
    "name": "John Doe",
    "email": "john.doe@example.com",
    "tel": "123-456-7890",
    "address-line1": "123 Main St",
    "address-line2": "Apt 4B",
    "address-level2": "Springfield",
    "address-level1": "CA",
    "postal-code": "62704",
    "country": "USA",
    "organization": "Example Corp",
    "username": "johndoe",
    "new-password": "securepassword123",
    "cc-name": "John Doe",
    "cc-number": "4111111111111111",
    "cc-exp": "12/25",
    "cc-csc": "123"
}

def wait_for_load(page, load_time_ms: int = 850):
    page.wait_for_load_state('load')
    page.wait_for_timeout(
        load_time_ms)

def fill_autofill_fields(page):
    input_elements = page.query_selector_all('input[autocomplete]')
    for input_element in input_elements:
        autocomplete_value = input_element.get_attribute('autocomplete')
        if autocomplete_value in user_info:
            print(autocomplete_value)
            try:
                input_element.fill(user_info[autocomplete_value], timeout=500)
            except:
                print(f"Failed filling in: {autocomplete_value}")



    select_elements = page.query_selector_all('select[autocomplete]')
    for element in select_elements:
        autocomplete_opt = element.get_attribute('autocomplete')
        if autocomplete_opt in user_info:
            element.select_option(value=user_info[autocomplete_opt])



# context = browser.new_context(
#     permissions=[]  # Deny all permissions by default
# )
#
# # Handle dialogs (alerts, confirms, prompts)
# context.on("dialog", lambda dialog: dialog.dismiss())
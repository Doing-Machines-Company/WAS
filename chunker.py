import time

from drivers import AxObservation
from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import pickle
from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from scrapecode.page_similarity import page_similarity
from scrapecode.element_similarity import element_similarity
from bs4 import BeautifulSoup
import re
import anthropic


client = anthropic.Anthropic(
    api_key="my_api_key",
)


PlaywrightPage = Any
CDPSession = Any
AxNode = Any  # TODO: make this a dataclass


@dataclass
class ActionInfo:
    action: Action
    before_html: str
    after_html: str
    before_screenshot: bytes | str
    after_screenshot: bytes | str


@dataclass
class PageState:
    url: str
    html: str
    actions: list[Action]


class EquivalenceClass:
    def __init__(self):
        self.page_urls = set()
        self.page_states: dict[str, PageState] = {}
        self.unique_actions: dict[str, ActionInfo] = {}
        # self.noted_divs = dict()  # New addition for storing div information
        # removed noted_divs, not needed bc models are not being used

    def add_page(self, state: PageState):
        normalized_url = normalize_url(state.url)
        self.page_urls.add(normalized_url)
        self.page_states[normalized_url] = state

    def update_unique_actions(self, actions: list[Action], before_html: str, after_html: str, before_screenshot: bytes,
                              after_screenshot: bytes):
        for action in actions:
            action_key = action.html
            if action_key not in self.unique_actions or not self.has_similar_action(action):
                self.unique_actions[action_key] = ActionInfo(action, before_html, after_html, before_screenshot,
                                                             after_screenshot)

    def has_similar_action(self, action: Action) -> bool:
        return any(element_similarity(action.html, a.action.html) >= 0.9 for a in self.unique_actions.values())

    def is_new_action(self, action: Action) -> bool:
        return not self.has_similar_action(action)

    def is_similar(self, url: str, html: str) -> bool:
        normalized_url = normalize_url(url)
        if normalized_url in self.page_urls:
            return True

        for page_url in self.page_urls:
            if page_similarity(html, self.page_states[page_url].html) < 0.8:
                return False

        return True


class EquivalenceClassSet:
    def __init__(self):
        self.classes: list[EquivalenceClass] = []
        self.added_urls: set[str] = set()
        self.common_actions = []

    def get_class(self, url: str, html: str) -> Optional[EquivalenceClass]:
        for eq_class in self.classes:
            if eq_class.is_similar(url, html):
                return eq_class
        return None

    def add_page(self, state: PageState, eq_class) -> EquivalenceClass:
        self.added_urls.add(normalize_url(state.url))
        if eq_class is None:
            # print(f"Creating new equivalence class")
            eq_class = EquivalenceClass()
            self.classes.append(eq_class)
        else:
            # print("Adding page to existing equivalence class")
            pass
        eq_class.add_page(state)
        return eq_class




# this is the aggressive normalization
def normalize_url(url: str) -> str:
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment



def get_chunks(PageState: str):
    client = None
    message = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1000,
        temperature=0,
        system="You are a website annotator.\nYou have a Python function annotate_general_functionality(description: str, indices: (int, int)), you are to call annotate_general_functionality for each general functionality.\nYou are going to be given an accessibility tree of a web page, where every action has the word 'ACTION' in its line. \nEvery line is indexed with a number in [].\nYour task is to identify chunks of the web page responsible for general tasks on the web page. Each general functionality is a chunk. Each chunk is a general functionality. A general functionality should encapsulate all instances of a type of action.\nYou should only care about general tasks that a user may want to do specifically on this web page. You must ignore navigation, ads or recommendations. Given these requirements, you must try to include all lines of the tree in some general functionality.\nEvery chunk should include actions, and chunks shouldn't have any overlap. \nFor every general functionality, give me the start and end indices of that chunk. Make your general functionality very inclusive and general. The indices are inclusive. If you are unsure about where to start the chunk, give the larger index. If you are unsure about where to end the chunk, give the smaller index.\nGeneral functionality may be a section of the website which performs the same type of action but on different instances of the same object type, group these into the same general functionality.\nIf a general functionality is within the chunk of another general functionality, I want to combine these into one general functionality. \n\nFirst reason step-by-step, then give me you answer in the form:\n- annotate_general_functionality('some general functionality which does something', (1, 30))\n- annotate_general_functionality('some other general functionality which does some other thing', (59, 62))",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Accessibility Tree:\n[0]RootWebArea: Your Orders\n[1]     ACTION of link: Skip to main content\n[2]     ACTION of link: Your Account\n[3]     StaticText: ›\n[4]     StaticText: Your Orders\n[5]     heading: Your Orders\n[6]     LayoutTable: \n[7]             generic: Search all orders\n[8]                     searchbox: Search all orders\n[9]             ACTION of button: Search Orders\n[10]                    StaticText: Submit\n[11]    tablist: \n[12]            tab: Orders\n[13]            tab: Buy Again\n[14]                    ACTION of link: Buy Again\n[15]            tab: Not Yet Shipped\n[16]                    ACTION of link: Not Yet Shipped\n[17]            tab: Digital Orders\n[18]                    ACTION of link: Digital Orders\n[19]            tab: Local Store Orders\n[20]                    ACTION of link: Local Store Orders\n[21]            tab: Cancelled Orders\n[22]                    ACTION of link: Cancelled Orders\n[23]    StaticText: 4 orders\n[24]    StaticText:  placed in\n[25]    combobox: 4 orders placed in\n[26]            ACTION of menuitem: last 30 days\n[27]            ACTION of menuitem: past 3 months\n[28]            ACTION of menuitem: 2024\n[29]            ACTION of menuitem: 2023\n[30]            ACTION of menuitem: 2022\n[31]            ACTION of menuitem: 2021\n[32]            ACTION of menuitem: Archived Orders\n[33]    StaticText: ORDER PLACED\n[34]    StaticText: March 18, 2024\n[35]    StaticText: TOTAL\n[36]    StaticText: $16.92\n[37]    StaticText: SHIP TO\n[38]    ACTION of link: James Chen \n[39]    StaticText: ORDER #\n[40]    StaticText: 112-3389185-0490669\n[41]    ACTION of link: View order details \n[42]    image: \n[43]    ACTION of link: View invoice\n[44]    StaticText: Delivered March 20\n[45]    ACTION of link: Innovera IVR10012 10 oz. Can Compressed Air Duster Cleaner (2/Pack)\n[46]            image: Innovera IVR10012 10 oz. Can Compressed Air Duster Cleaner (2/Pack)\n[47]    ACTION of link: Innovera IVR10012 10 oz. Can Compressed Air Duster Cleaner (2/Pack)\n[48]    ACTION of button: Buy it again\n[49]    ACTION of button: View your item\n[50]    ACTION of button: Get product support\n[51]    ACTION of button: Problem with order\n[52]    ACTION of button: Track package\n[53]    ACTION of button: Return or replace items\n[54]    ACTION of button: Write a product review\n[55]    ACTION of link: Archive order\n[56]    StaticText: ORDER PLACED\n[57]    StaticText: March 16, 2024\n[58]    StaticText: TOTAL\n[59]    StaticText: $23.31\n[60]    StaticText: SHIP TO\n[61]    ACTION of link: James Chen \n[62]    StaticText: ORDER #\n[63]    StaticText: 112-9999045-0853000\n[64]    ACTION of link: View order details \n[65]    image: \n[66]    ACTION of link: View invoice\n[67]    StaticText: Delivered March 19\n[68]    StaticText: Package was left inside the residence’s mailbox\n[69]    ACTION of link: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers for Face and Skin (72 Count)\n[70]            image: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers for Face and Skin (72 Count)\n[71]    ACTION of link: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers for Face and Skin (72 Count)\n[72]    StaticText: Return or replace items: Eligible through April 18, 2024\n[73]    ACTION of button: Buy it again\n[74]    ACTION of button: View your item\n[75]    ACTION of button: Track package\n[76]    ACTION of button: Return or replace items\n[77]    ACTION of button: Share gift receipt\n[78]    ACTION of button: Get help\n[79]    ACTION of button: Write a product review\n[80]    ACTION of link: Archive order\n[81]    StaticText: ORDER PLACED\n[82]    StaticText: March 9, 2024\n[83]    StaticText: TOTAL\n[84]    StaticText: $27.59\n[85]    StaticText: SHIP TO\n[86]    ACTION of link: James Chen \n[87]    StaticText: ORDER #\n[88]    StaticText: 112-1099104-8569006\n[89]    ACTION of link: View order details \n[90]    image: \n[91]    ACTION of link: View invoice\n[92]    StaticText: Delivered March 11\n[93]    StaticText: Your package was left in the mail room.\n[94]    ACTION of link: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega Rolls= 132 Regular Rolls), 388 Sheets per Roll, Packaging May Vary\n[95]            image: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega Rolls= 132 Regular Rolls), 388 Sheets per Roll, Packaging May Vary\n[96]    ACTION of link: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega Rolls= 132 Regular Rolls), 388 Sheets per Roll, Packaging May Vary\n[97]    StaticText: Return or replace items: Eligible through April 10, 2024\n[98]    ACTION of button: Buy it again\n[99]    ACTION of button: View your item\n[100]   ACTION of button: Track package\n[101]   ACTION of button: Return or replace items\n[102]   ACTION of button: Share gift receipt\n[103]   ACTION of button: Write a product review\n[104]   ACTION of link: Archive order\n[105]   StaticText: ORDER PLACED\n[106]   StaticText: February 16, 2024\n[107]   StaticText: TOTAL\n[108]   StaticText: $14.83\n[109]   StaticText: SHIP TO\n[110]   ACTION of link: James Chen \n[111]   StaticText: ORDER #\n[112]   StaticText: 112-3769458-4341800\n[113]   ACTION of link: View order details \n[114]   image: \n[115]   ACTION of link: View invoice\n[116]   StaticText: Delivered February 18\n[117]   StaticText: Package was left inside the residence’s mailbox\n[118]   ACTION of link: CeraVe Body Wash with Salicylic Acid | Fragrance Free Body Wash to Exfoliate Rough and Bumpy Skin | Allergy Tested | 10 Ounce\n[119]           image: CeraVe Body Wash with Salicylic Acid | Fragrance Free Body Wash to Exfoliate Rough and Bumpy Skin | Allergy Tested | 10 Ounce\n[120]   ACTION of link: CeraVe Body Wash with Salicylic Acid | Fragrance Free Body Wash to Exfoliate Rough and Bumpy Skin | Allergy Tested | 10 Ounce\n[121]   StaticText: Return window closed on March 19, 2024\n[122]   ACTION of button: Buy it again\n[123]   ACTION of button: View your item\n[124]   ACTION of button: Get product support\n[125]   ACTION of button: Track package\n[126]   ACTION of button: Write a product review\n[127]   ACTION of link: Archive order\n[128]   heading: Buy it again\n[129]   ACTION of link: Tony's Chocolonely Assortment - Hazelnut, Dark Pretzel & Toffee, Caramel Sea Salt, Chocolate Bars, No Artificial Flavoring - \n[130]           image: Tony's Chocolonely Assortment - Hazelnut, Dark Pretzel & Toffee, Caramel Sea Salt, Chocolate Bars, No Artificial Flavoring - \n[131]   ACTION of link: Tony's Chocolonely Assortment - Hazelnut, Dark Pretzel & Toffee, Caramel Sea Salt, Chocolate Bars, No Artificial Flavoring - 4 Bars $21.57  \n[132]   ACTION of button: Add to Cart\n[133]           StaticText: Submit\n[134]   ACTION of link: OPTIMUM NUTRITION Gold Standard Pre-Workout with Creatine, Beta-Alanine, and Caffeine for Energy, Flavor: Fruit Punch, 30 Ser\n[135]           image: OPTIMUM NUTRITION Gold Standard Pre-Workout with Creatine, Beta-Alanine, and Caffeine for Energy, Flavor: Fruit Punch, 30 Ser\n[136]   ACTION of link: OPTIMUM NUTRITION Gold Standard Pre-Workout with Creatine, Beta-Alanine, and Caffeine for Energy, Flavor: Fruit Punch, 30 Servings $23.88   Purchased Aug 2023\n[137]   ACTION of button: Add to Cart\n[138]           StaticText: Submit\n[139]   ACTION of link: Brita Standard Water Filter, BPA-Free, Replaces 1,800 Plastic Water Bottles a Year, Lasts Two Months or 40 Gallons, Includes \n[140]           image: Brita Standard Water Filter, BPA-Free, Replaces 1,800 Plastic Water Bottles a Year, Lasts Two Months or 40 Gallons, Includes \n[141]   ACTION of link: Brita Standard Water Filter, BPA-Free, Replaces 1,800 Plastic Water Bottles a Year, Lasts Two Months or 40 Gallons, Includes 6 Filters, Kitchen Essential $29.68   Purchased Aug 2022\n[142]   ACTION of button: Add to Cart\n[143]           StaticText: Submit\n[144]   ACTION of link: Soak Wash - Scentless 12 oz Laundry Detergent\n[145]           image: Soak Wash - Scentless 12 oz Laundry Detergent\n[146]   ACTION of link: Soak Wash - Scentless 12 oz Laundry Detergent $16.94   Purchased Jan 2023\n[147]   ACTION of button: Add to Cart\n[148]           StaticText: Submit\n[149]   ACTION of link: Gorilla All Weather Outdoor Waterproof Duct Tape, UV and Temperature Resistant, 1.88\" x 25 yd, Black, (Pack of 1)\n[150]           image: Gorilla All Weather Outdoor Waterproof Duct Tape, UV and Temperature Resistant, 1.88\" x 25 yd, Black, (Pack of 1)\n[151]   ACTION of link: Gorilla All Weather Outdoor Waterproof Duct Tape, UV and Temperature Resistant, 1.88\" x 25 yd, Black, (Pack of 1) $12.20   Purchased Aug 2022\n[152]   ACTION of button: Add to Cart\n[153]           StaticText: Submit\n[154]   ACTION of link: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers f\n[155]           image: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers f\n[156]   ACTION of link: Hero Cosmetics Mighty Patch™ Original Patch - Hydrocolloid Acne Pimple Patch for Covering Zits and Blemishes, Spot Stickers for Face and Skin (72 Count) $21.99   Purchased Mar 2024\n[157]   ACTION of button: Add to Cart\n[158]           StaticText: Submit\n[159]   ACTION of link: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega \n[160]           image: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega \n[161]   ACTION of link: Cottonelle Ultra Clean Toilet Paper with Active CleaningRipples, 1- Ply, 24 Family Mega Rolls (4 Packs of 6) (24 Family Mega Rolls= 132 Regular Rolls), 388 Sheets per Roll, Packaging May Vary $24.83   Purchased Mar 2024\n[162]   ACTION of button: Add to Cart\n[163]           StaticText: Submit"
                    }
                ]
            }
        ]
    )
    print(message.content)

def get_bounds(page_state: PageState, indices: (int, int)):
    start, end = indices
    pass
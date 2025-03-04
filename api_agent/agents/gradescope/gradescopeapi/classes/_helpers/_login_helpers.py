import requests
from bs4 import BeautifulSoup

from agents.gradescope.gradescopeapi import DEFAULT_GRADESCOPE_BASE_URL

import aiohttp

async def get_auth_token_init_gradescope_session(
    session: aiohttp.ClientSession,
    gradescope_base_url: str = DEFAULT_GRADESCOPE_BASE_URL,
) -> str:
    """
    Go to homepage to parse hidden authenticity token and to set initial "_gradescope_session" cookie
    """
    # Go to homepage and set initial "_gradescope_session" cookie.
    async with session.get(gradescope_base_url) as homepage_resp:
        homepage_text = await homepage_resp.text()
    
    homepage_soup = BeautifulSoup(homepage_text, "html.parser")
    
    # Find the authenticity token using CSS selectors.
    auth_token = homepage_soup.select_one(
        'form[action="/login"] input[name="authenticity_token"]'
    )["value"]
    return auth_token


async def login_set_session_cookies(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    auth_token: str,
    gradescope_base_url: str = DEFAULT_GRADESCOPE_BASE_URL,
) -> bool:
    GS_LOGIN_ENDPOINT = f"{gradescope_base_url}/login"

    # Populate parameters for the POST request to the login endpoint.
    login_data = {
        "utf8": "✓",
        "session[email]": email,
        "session[password]": password,
        "session[remember_me]": 0,
        "commit": "Log In",
        "session[remember_me_sso]": 0,
        "authenticity_token": auth_token,
    }

    # Send the POST request to the login endpoint.
    async with session.post(GS_LOGIN_ENDPOINT, params=login_data) as login_resp:
        login_resp_text = await login_resp.text()
        # Check for a redirect in the response history (302 Found)
        if login_resp.history and login_resp.history[0].status == 302:
            soup = BeautifulSoup(login_resp_text, "html.parser")
            csrf_token = soup.select_one('meta[name="csrf-token"]')["content"]
            
            # Update the session headers with the CSRF token.
            # Note: If session.headers is immutable, you can update session._default_headers instead.
            try:
                session.headers.update({"X-CSRF-Token": csrf_token})
            except AttributeError:
                session._default_headers["X-CSRF-Token"] = csrf_token
            return True
        return False


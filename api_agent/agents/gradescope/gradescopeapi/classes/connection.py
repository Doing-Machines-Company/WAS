import requests

from agents.gradescope.gradescopeapi import DEFAULT_GRADESCOPE_BASE_URL
from agents.gradescope.gradescopeapi.classes._helpers._login_helpers import (
    get_auth_token_init_gradescope_session,
    login_set_session_cookies,
)
from agents.gradescope.gradescopeapi.classes.account import Account
from proxy_utils import create_proxy_auth

import aiohttp
import asyncio

class GSConnection:
    def __init__(self, gradescope_base_url: str = DEFAULT_GRADESCOPE_BASE_URL):
        # Create an aiohttp session for asynchronous HTTP calls.
        self.session = aiohttp.ClientSession()
        self.proxy_auth = None 
        self.gradescope_base_url = gradescope_base_url
        self.logged_in = False
        self.account = None

    async def login(self, email, password):
        # Go to homepage to parse hidden authenticity token and set initial session cookie.
        # Assuming that get_auth_token_init_gradescope_session has been updated to an async version.
        self.proxy_auth = await create_proxy_auth() #create a unique (sticky) proxy session for this connection
        auth_token = await get_auth_token_init_gradescope_session(self.session, self.proxy_auth, self.gradescope_base_url)
        
        # Login and set cookies in the session.
        # Assuming that login_set_session_cookies has also been updated to an async version.
        login_success = await login_set_session_cookies(
            self.session, self.proxy_auth, email, password, auth_token, self.gradescope_base_url
        )
        if login_success:
            self.logged_in = True
            self.account = Account(self.session, self.proxy_auth, self.gradescope_base_url)
        else:
            raise ValueError("Invalid credentials.")

    async def close(self):
        # Properly close the aiohttp session when done.
        await asyncio.sleep(0)
        await self.session.close()


# proxy_utils.py
import os
import asyncio
import itertools
import aiohttp
import dotenv 
# Starting session id; adjust as necessary.
SESSION_ID_START = 338703999
session_id_counter = itertools.count(SESSION_ID_START)
session_id_lock = asyncio.Lock()

dotenv.load_dotenv()

async def get_next_session_id() -> int:
    async with session_id_lock:
        return next(session_id_counter)

async def create_proxy_auth() -> aiohttp.BasicAuth:
    sessid = await get_next_session_id()
    proxy_username = f"customer-{os.getenv('OXYLABS_USERNAME')}-cc-us-sessid-0{sessid}-sesstime-5"
    proxy_password = os.getenv('OXYLABS_PASSWORD')
    return aiohttp.BasicAuth(proxy_username, proxy_password)

import asyncio
import pickle
import re
import shutil
import urllib
from asyncio import Queue
from pathlib import Path

import aiofiles

from models import URLStateManager


async def load_file(path:Path):
    async with aiofiles.open(path, 'rb') as f:
        return pickle.loads(await f.read())
async def read_from_checkpoint(output_dir:str):

    scraper_state_path = Path(output_dir) / 'scraper_state.pkl'
    checkpoint_path = Path(output_dir) / 'checkpoint.pkl'

    if scraper_state_path.exists() and checkpoint_path.exists():
        equiv_classes = await load_file(scraper_state_path)
        resumed_action_number, urls, seen_urls = await load_file(checkpoint_path)

        url_queue = Queue()
        for url_info in urls:
            await url_queue.put(url_info)
        # remove partially filled urlstate
        cleaned_url = re.sub(r'^(https?://)?(www\.)?', '', urls[0][0])
        cleaned_url = cleaned_url.rstrip('/')
        old_urlstate_path = Path(output_dir) / urllib.parse.quote(cleaned_url, safe='')
        if old_urlstate_path.exists():
            shutil.rmtree(old_urlstate_path)
            print("Removed partially explored urlstate")
        print("Resuming exploration from ", urls[0][0])
        return url_queue, seen_urls, equiv_classes, resumed_action_number
    else:
        print("Couldn't find checkpoint and state files for resume. Starting from scratch")

async def save_checkpoint(output_dir:str,url_queue:Queue, seen_urls: set[str], equiv_classes: URLStateManager, action_number:int):
    output_path = Path(output_dir) / 'scraper_state.pkl'
    checkpoint_path = Path(output_dir) / 'checkpoint.pkl'

    urls = list(url_queue._queue)  # Accessing the protected member _queue

    async with aiofiles.open(output_path, 'wb') as f:
        await asyncio.to_thread(pickle.dump, equiv_classes, f)  # Run pickle.dump in a thread
    async with aiofiles.open(checkpoint_path, 'wb') as f:
        await asyncio.to_thread(pickle.dump, (action_number, urls, seen_urls), f)

    print("Saved checkpoint")

    # special_output_path = Path('special_dominos') / 'special_scraper_state.pkl'
    # special_checkpoint_path = Path('special_dominos') / 'special_checkpoint.pkl'
    #
    # if urls != [] and 'www.dominos.com/en/pages/order/#!/checkout' in urls[0][0]:
    #     print("Saved special checkpoint")
    #     with open(special_output_path, 'wb') as f:
    #         pickle.dump(equiv_classes, f)  # url_queue and current url needed for resume purposes
    #     with open(special_checkpoint_path, 'wb') as f:
    #         pickle.dump((action_number, urls, seen_urls), f)
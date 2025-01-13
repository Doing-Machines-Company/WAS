# main.py

import asyncio
import logging

from canvas_api_agent import CanvasAPIAgent
from api_functions import CanvasAPIHandler

logging.basicConfig(level=logging.INFO)

async def main():
    canvas_handler = CanvasAPIHandler()
    agent = CanvasAPIAgent()



    # Let it run for 2 minutes
    agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
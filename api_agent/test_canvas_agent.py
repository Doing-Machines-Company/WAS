# main.py

import asyncio
import logging

from canvas_api_agent import CanvasAPIAgent
from api_functions import CanvasAPIHandler

logging.basicConfig(level=logging.INFO)

async def main():
    # canvas_handler = CanvasAPIHandler()
    agent = CanvasAPIAgent()
    print(agent.task)
    # action = await agent.call_action()
    # print(action.parsed_output)
    # courses = canvas_handler.perform_action(action.parsed_output)
    # print(courses)
    # # Let it run for 2 minutes
    # agent.stop()
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
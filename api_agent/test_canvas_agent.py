# test_canvas_agent.py

import asyncio
import logging

from agents.canvas.canvas_api_agent import CanvasAPIAgent

logging.basicConfig(level=logging.INFO)


async def main():
    # Instantiate the Canvas agent
    agent = CanvasAPIAgent()
    print("Agent task:", agent.task)

    # Run the agent. It will loop, call the LLM for next actions, etc.
    # You can stop it manually or let the STOP action from LLM end it.
    await agent.run()

    # Optionally, do any post-run checks or prints
    print("Agent run has completed.")
    input(agent.get_poll_output())

if __name__ == "__main__":
    asyncio.run(main())

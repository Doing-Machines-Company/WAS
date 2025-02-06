# test_canvas_agent.py

import asyncio
import logging

from agents.canvas.canvas_api_agent import CanvasAPIAgent
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent


logging.basicConfig(level=logging.INFO)

"""

import asyncio
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I have a birthday for James Chan on Feb 10."
    )
    asyncio.run(agent.run())


"""

async def main():
    # Instantiate the Canvas agent
    agent = CanvasAPIAgent()
    print("Agent task:", agent.task)

    # Run the agent. It will loop, call the LLM for next actions, etc.
    # You can stop it manually or let the STOP action from LLM end it.
    await agent.run()

    # Optionally, do any post-run checks or prints
    print("Agent run has completed.")
    poll_out = agent.get_poll_output()

    input(poll_out)

    step_size = 1

    for i in range(0, len(poll_out), step_size):
        cur_chunk = poll_out[i:i + step_size]
        task_string = ""
        for i, linmem in enumerate(cur_chunk):
            task_string += f"{i})\nCall: \n{linmem.call}\nReceived: \n{linmem.received}\n"
        input(task_string)
        skip = input("SKIP?")
        if skip == "":
            agent = GCalGTasksAPIAgent(
                task=task_string,
                from_user=False
            )
            await agent.run()
        else:
            continue


if __name__ == "__main__":
    asyncio.run(main())

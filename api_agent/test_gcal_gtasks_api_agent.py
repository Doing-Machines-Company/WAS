import asyncio
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I have a birthday for James Chan on Feb 10."
    )
    asyncio.run(agent.run())

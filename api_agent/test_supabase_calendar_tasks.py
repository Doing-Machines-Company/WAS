# test_supabase_calendar_tasks.py

import asyncio
import logging

from agents.supabase_cal_task.supabase_calendar_tasks_api_agent_multi import SupabaseCalendarTasksAPIAgentMulti


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

if __name__ == "__main__":
    # Example usage:
    agent = SupabaseCalendarTasksAPIAgentMulti(
        task="Add a new 'Clean my desk' task.",
        user_id="123e4567-e89b-12d3-a456-426614174000"
    )
    asyncio.run(agent.run())

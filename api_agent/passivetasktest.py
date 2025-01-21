# passivetasktest.py

import asyncio
import logging

from google_tasks_change import GTasksChangeAgent
from api_functions import GoogleTasksAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(task_data: dict) -> bool:
    """
    Example filter: returns True if 'important' (case-insensitive)
    appears in the task's title.
    """
    title = task_data.get("title", "") or ""
    return "important" in title.lower()
    # return True
def on_new_tasks_callback(new_items):
    print(f"\n[CALLBACK] Received {len(new_items)} new/updated matching task(s):")
    for t in new_items:
        t_id = t.get("id", "??")
        title = t.get("title", "")
        print(f"  - taskId={t_id}, title={title[:50]}...")

async def main():
    tasks_handler = GoogleTasksAPIHandler()

    # Suppose you already know these task list IDs from listing them
    my_tasklist_ids = []  # empty to do everything

    agent = GTasksChangeAgent(
        check_interval_seconds=10,
        tasks_handler=tasks_handler,
        criteria_func=my_criteria_func,
        tasklist_ids=my_tasklist_ids
    )

    # Register a callback for newly matching tasks
    agent.on_new_tasks = on_new_tasks_callback

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for 2 minutes
    await asyncio.sleep(120)
    agent.stop()
    await task

    # After it stops, print all matched items
    matched = agent.get_matching_tasks()
    print(f"\nTotal matched tasks: {len(matched)}")
    for t in matched:
        print(f" - ID={t.get('id')}, title={t.get('title', '')}")

if __name__ == "__main__":
    asyncio.run(main())
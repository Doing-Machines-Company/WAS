# passivetasktest.py

import asyncio
import logging

from agents.gcal.google_tasks_change import GTasksChangeAgent
from api_functions import GoogleTasksAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(task_data: dict) -> bool:
    """
    Example filter #1: returns True if 'important' (case-insensitive)
    appears in the task's title.
    """
    title = task_data.get("title", "") or ""
    return "important" in title.lower()

def my_alt_criteria_func(task_data: dict) -> bool:
    """
    Example filter #2 for new_criteria_reset:
    returns True if 'demo' (case-insensitive) appears in the task's title.
    """
    title = task_data.get("title", "") or ""
    return "demo" in title.lower()

def on_tracked_change(changes: dict):
    """
    Callback receives a dict of task_id -> {"data": <task_data>, "just_changed": bool}.
    """
    print(changes)
    # 1) Log all tasks we received
    logging.info(f"[CALLBACK] Received {len(changes)} task(s) this cycle:")
    for t_id, info in changes.items():
        task_data = info["data"]
        logging.info(f"  - taskId={t_id}, title='{task_data.get('title','')}'")

    # 2) Identify which tasks had just_changed=True
    changed = [t_id for t_id, info in changes.items() if info["just_changed"]]
    if changed:
        logging.info(f"[CALLBACK] Of these, {len(changed)} task(s) were newly updated/changed:")
        for t_id in changed:
            task_data = changes[t_id]["data"]
            logging.info(f"     * taskId={t_id}, title='{task_data.get('title','')}'")
    else:
        logging.info("[CALLBACK] None of these tasks changed this time.")

async def main():
    tasks_handler = GoogleTasksAPIHandler()

    # Provide a list of tasklists or leave empty to watch all
    my_tasklist_ids = []

    agent = GTasksChangeAgent(
        check_interval_seconds=5,
        tasks_handler=tasks_handler,
        criteria_func=my_criteria_func,  # start with the "important" filter
        tasklist_ids=my_tasklist_ids
    )

    agent.on_tracked_change = on_tracked_change

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for 30 seconds
    logging.info("Running with 'my_criteria_func' (searching 'important') for 30 seconds...")
    await asyncio.sleep(60)

    # Switch to alternate criteria
    logging.info("\n=== Switching criteria to 'my_alt_criteria_func' (searching 'demo') ===\n")
    await agent.new_criteria_reset(my_alt_criteria_func)

    # Let it run another 30 seconds
    logging.info("Running with 'my_alt_criteria_func' for 30 seconds...")
    await asyncio.sleep(45)

    agent.stop()
    await task

    # After it stops, print all matched items
    # (final criteria is 'my_alt_criteria_func')
    matched = agent.get_active_tasks()
    print(f"\nTotal matched tasks after stop: {len(matched)}")
    for t in matched:
        print(f" - ID={t.get('id')}, title={t.get('title', '')}")

if __name__ == "__main__":
    asyncio.run(main())
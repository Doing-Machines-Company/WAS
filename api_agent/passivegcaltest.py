# passivegcaltest.py

import asyncio
import logging

from google_calender_event_change import GCalEventChangeAgent
from api_functions import GoogleCalendarAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(event_data: dict) -> bool:
    """
    For example: Return True if 'meeting' is in the event summary.
    Or, return True for everything if you want to track all events.
    """
    summary = event_data.get("summary", "") or ""
    return "meeting" in summary.lower()

def on_tracked_event_changed(change_info: dict):
    """
    Called whenever a tracked event is created/updated/deleted
    (i.e. in _active_tracking_set).
    """
    ev_id = change_info["id"]
    change_type = change_info["change_type"]
    diffs = change_info["diffs"]
    print(f"[TRACKED CHANGE] eventId={ev_id}, type={change_type}, diffs={diffs}")

async def main():
    calendar_handler = GoogleCalendarAPIHandler()

    # We'll watch from 12 hours in the past up to 72 hours in the future
    agent = GCalEventChangeAgent(
        check_interval_seconds=10,
        calendar_handler=calendar_handler,
        criteria_func=my_criteria_func,
        time_window_past_hours=12,
        time_window_future_hours=72,
        calendar_ids=["primary"],  # or multiple IDs
        last_sync_token=None       # Start fresh => full fetch first
    )

    # This callback fires whenever a tracked event is created/updated/deleted
    agent.on_tracked_change = on_tracked_event_changed

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for ~1 minute
    await asyncio.sleep(240)

    # Optionally, do a new criteria reset
    # new_criteria = lambda ev: "zoom" in (ev.get("summary","").lower())
    # await agent.new_criteria_reset(new_criteria)

    # Stop the agent
    agent.stop()
    await task

    # Report on final tracked events
    tracked_events = agent.get_active_tracked_events()
    print(f"\n[RESULT] Currently tracking {len(tracked_events)} event(s) after stop:")
    for ev in tracked_events:
        print(f"  - ID={ev.get('id')}, summary={ev.get('summary', '')}")

    # Also see all changes recorded
    all_changes = agent.get_all_changes()
    print(f"\n[RESULT] We recorded {len(all_changes)} total changes in _all_changes.")
    for idx, ch in enumerate(all_changes, 1):
        print(f"  {idx}. {ch}")

if __name__ == "__main__":
    asyncio.run(main())

# passivegcaltest.py

import asyncio
import logging

from google_calendar_event_change import GCalEventChangeAgent
from api_functions import GoogleCalendarAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(event_data: dict) -> bool:
    """
    Example criteria: Return True if 'meeting' is in the event summary.
    """
    summary = event_data.get("summary", "") or ""
    return "meeting" in summary.lower()

def my_new_criteria_func(event_data: dict) -> bool:
    """
    A second criteria for testing new_criteria_reset:
    Return True if 'zoom' is in the event summary.
    """
    summary = event_data.get("summary", "") or ""
    return "zoom" in summary.lower()

def on_tracked_change(changes: dict):
    """
    `changes` is a dictionary:
        {
          "<event_id>": {
              "data": <the_event_dict>,
              "just_changed": bool
          }, ...
        }
    """
    # 1) Log all items in the dictionary
    logging.info(f"[CALLBACK] Received {len(changes)} event(s) in this poll cycle:")
    for ev_id, info in changes.items():
        ev_data = info["data"]
        summary = ev_data.get("summary", "")
        logging.info(f"  - eventId={ev_id}, summary={summary}")

    # 2) Now, log which items had just_changed=True
    updated = [ev_id for ev_id, info in changes.items() if info["just_changed"]]
    if updated:
        logging.info(f"[CALLBACK] Of these, {len(updated)} event(s) were updated/changed:")
        for ev_id in updated:
            ev_data = changes[ev_id]["data"]
            summary = ev_data.get("summary", "")
            logging.info(f"     * eventId={ev_id}, summary={summary}")
    else:
        logging.info(f"[CALLBACK] None of these items changed this time.")

async def main():
    calendar_handler = GoogleCalendarAPIHandler()

    # We'll watch from 12 hours in the past up to 72 hours in the future
    agent = GCalEventChangeAgent(
        check_interval_seconds=5,
        calendar_handler=calendar_handler,
        criteria_func=my_criteria_func,
        time_window_past_hours=12,
        time_window_future_hours=72,
        calendar_ids=["primary"],  # or multiple IDs
        last_sync_token=None       # Start fresh => full fetch first
    )

    # This callback fires whenever we do a poll
    agent.on_tracked_change = on_tracked_change

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for 45 seconds
    logging.info("Running with my_criteria_func (searching 'meeting') for 45 seconds...")
    await asyncio.sleep(20)

    # Test new_criteria_reset
    logging.info("\n=== Now calling new_criteria_reset to switch to 'zoom' in summary ===\n")
    await agent.new_criteria_reset(my_new_criteria_func)

    # Let it run for another 45 seconds
    logging.info("Running with new_criteria_func (searching 'zoom') for another 45 seconds...")
    await asyncio.sleep(45)

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

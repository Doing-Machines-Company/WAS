# passivegcaltest.py

import asyncio
import logging

from google_calender_event_change import GCalEventChangeAgent
from api_functions import GoogleCalendarAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(event_data: dict) -> bool:
    """
    Simple filter example: returns True if 'awesome' (case-insensitive)
    appears in the event's summary.
    """
    summary = event_data.get("summary", "") or ""
    # return "bonk" in summary.lower()
    return True
def on_new_events_callback(new_items):
    print(f"\n[CALLBACK] Received {len(new_items)} new item(s):")
    for ev in new_items:
        ev_id = ev.get("id", "??")
        summary = ev.get("summary", "")
        print(f"  - eventId={ev_id}, summary={summary[:50]}...")

async def main():
    calendar_handler = GoogleCalendarAPIHandler()

    agent = GCalEventChangeAgent(
        check_interval_seconds=10,
        calendar_handler=calendar_handler,
        criteria_func=my_criteria_func,
        calendar_ids=["primary"],   # or multiple IDs
        last_sync_token=None        # Start fresh => do full fetch first
    )

    # Register a callback to be notified of new/changed events that match the criteria
    agent.on_new_events = on_new_events_callback

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for 2 minutes
    await asyncio.sleep(120)
    agent.stop()
    await task

    # After it stops, print all matched items
    matched = agent.get_matching_events()
    print(f"\nTotal matched events: {len(matched)}")
    for ev in matched:
        print(f" - ID={ev.get('id')}, summary={ev.get('summary', '')}")

if __name__ == "__main__":
    asyncio.run(main())
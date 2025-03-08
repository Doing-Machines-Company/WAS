# db-to-google_test.py

import os
import asyncio
import signal
from datetime import datetime, timezone
from typing import Dict, Any

from google.oauth2.credentials import Credentials

from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler

# NEW: Imports for Google Tasks
from handlers.async_gtasks_handler import AsyncGoogleTasksAPIHandler
from api_agent_classes import APIAction, APIActionType

# Calendar param classes
from handler_parameters.api_actions_params_gcal import (
    CalendarCreateEventParams,
    CalendarListCalendarsParams
)

# NEW: Tasks param classes
from handler_parameters.api_actions_params_gtasks import (
    TasksListTasklistsParams,
    TasksCreateTasklistParams,
    TasksCreateTaskParams
)

DEFAULT_CALENDAR_NAME = "inbound.fyi"
# NEW: Tasklist name to use or create
DEFAULT_TASKLIST_NAME = "inbound.fyi"

# Track tasks so we can clean them up on shutdown
pending_tasks = set()

# We'll use an asyncio.Event to coordinate graceful shutdown
shutdown_event = asyncio.Event()


async def find_or_create_calendar(gcal_handler, calendar_name: str) -> str:
    """
    Find a calendar by name or create it if it doesn't exist.

    Args:
        gcal_handler: Instance of AsyncGoogleCalendarAPIHandler
        calendar_name: Name of the calendar to find or create

    Returns:
        str: The ID of the found or created calendar
    """
    print(f"Looking for calendar: '{calendar_name}'...")

    # List existing calendars
    calendars = await gcal_handler.perform_action(
        APIAction(
            action_type=APIActionType.CALENDAR_LIST_CALENDARS,
            reason=f"Looking for calendar '{calendar_name}'",
            parameters=vars(CalendarListCalendarsParams())
        )
    )

    # Check if calendar exists
    for calendar in calendars:
        if calendar.get('summary') == calendar_name:
            print(f"Found existing calendar: '{calendar_name}' (ID: {calendar['id']})")
            return calendar['id']

    # Calendar not found, use primary calendar as fallback
    print(f"Calendar '{calendar_name}' not found. Using 'primary' calendar as fallback.")
    return 'primary'


# NEW: Find or create a tasklist by name
async def find_or_create_tasklist(gtasks_handler, tasklist_name: str) -> str:
    """
    Find a tasklist by title or create it if it doesn't exist.

    Args:
        gtasks_handler: Instance of AsyncGoogleTasksAPIHandler
        tasklist_name: Name of the tasklist to find or create

    Returns:
        str: The ID of the found or created tasklist
    """
    print(f"Looking for tasklist: '{tasklist_name}'...")

    # List existing tasklists
    tasklists = await gtasks_handler.perform_action(
        APIAction(
            action_type=APIActionType.TASKS_LIST_TASKLISTS,
            reason=f"Looking for tasklist '{tasklist_name}'",
            parameters=vars(TasksListTasklistsParams())
        )
    )

    # Check if tasklist exists
    for tl in tasklists:
        if tl.get('title') == tasklist_name:
            print(f"Found existing tasklist: '{tasklist_name}' (ID: {tl['id']})")
            return tl['id']

    # Tasklist not found, create one
    print(f"Tasklist '{tasklist_name}' not found. Creating a new tasklist...")
    new_tl = await gtasks_handler.perform_action(
        APIAction(
            action_type=APIActionType.TASKS_CREATE_TASKLIST,
            reason=f"Creating tasklist '{tasklist_name}'",
            parameters=vars(TasksCreateTasklistParams(title=tasklist_name))
        )
    )

    if new_tl and "id" in new_tl:
        print(f"Created new tasklist '{tasklist_name}' (ID: {new_tl['id']})")
        return new_tl['id']

    # As a fallback, if creation fails, return '@default'
    print("Tasklist creation failed. Defaulting to '@default' tasklist.")
    return "@default"


async def sync_supabase_to_gcal(
        supabase_handler,
        gcal_handler,
        user_id: str,
        gcal_id: str = 'primary',
        time_zone: str = None
) -> Dict[str, Any]:
    """
    Syncs calendar events from Supabase to Google Calendar.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        gcal_handler: Instance of AsyncGoogleCalendarAPIHandler
        user_id: Supabase user ID to filter events by
        gcal_id: Google Calendar ID to add events to (default: 'primary')
        time_zone: Time zone to use for events (default: None)

    Returns:
        Dictionary with sync statistics
    """
    # Get all calendar events for the user from Supabase
    supabase_events = await supabase_handler.perform_action(
        APIAction(
            action_type=APIActionType.SUPABASE_LIST_CALENDAR_EVENTS,
            reason="Fetching calendar events for sync",
            parameters={"user_id": user_id}
        )
    )

    stats = {
        "total_events": len(supabase_events),
        "events_synced": 0,
        "events_skipped": 0,
        "sync_errors": 0,
        "details": []
    }

    print(f"Found {len(supabase_events)} events in Supabase calendar")

    # Process each Supabase event
    for event in supabase_events:
        event_name = event.get("name", "(Unnamed event)")
        event_id = event.get("id")

        print(f"Processing event: {event_name} (ID: {event_id})")

        # Skip events that have already been synced unless they've been updated since
        if "gcal_event_id" in event.get("metadata", {}) and not event.get("metadata", {}).get("updated_since_sync",
                                                                                              False):
            stats["events_skipped"] += 1
            stats["details"].append({
                "event_id": event_id,
                "name": event_name,
                "status": "skipped",
                "reason": "Already synced"
            })
            print(f"  - Skipping: Already synced to Google Calendar")
            continue

        # Create Google Calendar event
        try:
            # Map Supabase event fields to Google Calendar event fields
            event_params = CalendarCreateEventParams(
                summary=event_name,
                description=event.get("description", ""),
                calendarId=gcal_id,
                start=event["start"],
                end=event["end"],
                timeZone=time_zone,
            )

            # Add location from metadata if it exists
            if event.get("metadata", {}).get("location"):
                event_params.location = event["metadata"]["location"]

            print(f"  - Creating event in Google Calendar: {event_name}")

            # Create the event in Google Calendar
            gcal_event = await gcal_handler.perform_action(
                APIAction(
                    action_type=APIActionType.CALENDAR_CREATE_EVENT,
                    reason=f"Creating event '{event_name}' in Google Calendar",
                    parameters=vars(event_params)
                )
            )

            if gcal_event and "id" in gcal_event:
                print(f"  - Event created successfully. GCal ID: {gcal_event['id']}")
                metadata = event.get("metadata", {}) or {}
                metadata.update({
                    "gcal_event_id": gcal_event["id"],
                    "gcal_html_link": gcal_event.get("htmlLink", ""),
                    "last_synced": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "updated_since_sync": False
                })

                print(f"  - Updating Supabase event with sync metadata")
                await supabase_handler.perform_action(
                    APIAction(
                        action_type=APIActionType.SUPABASE_UPDATE_CALENDAR_EVENT,
                        reason=f"Updating event '{event_name}' with sync metadata",
                        parameters={
                            "event_id": event_id,
                            "user_id": user_id,
                            "fields_to_update": {"metadata": metadata}
                        }
                    )
                )

            stats["events_synced"] += 1
            stats["details"].append({
                "event_id": event_id,
                "name": event_name,
                "status": "synced",
                "gcal_event_id": gcal_event.get("id") if gcal_event else None
            })
            print(f"  - Sync complete for event: {event_name}")

        except Exception as e:
            print(f"  - ERROR syncing event: {str(e)}")
            stats["sync_errors"] += 1
            stats["details"].append({
                "event_id": event_id,
                "name": event_name,
                "status": "error",
                "error": str(e)
            })

    print("\nSync Summary:")
    print(f"Total events: {stats['total_events']}")
    print(f"Synced: {stats['events_synced']}")
    print(f"Skipped: {stats['events_skipped']}")
    print(f"Errors: {stats['sync_errors']}")

    return stats


# NEW: Sync tasks from Supabase to Google Tasks
async def sync_supabase_to_gtasks(
        supabase_handler,
        gtasks_handler,
        user_id: str,
        tasklist_id: str = "@default"
) -> Dict[str, Any]:
    """
    Sync tasks from Supabase to Google Tasks.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        gtasks_handler: Instance of AsyncGoogleTasksAPIHandler
        user_id: Supabase user ID to filter tasks by
        tasklist_id: Google tasklist ID to add tasks to (default: '@default')

    Returns:
        Dictionary with sync statistics
    """
    # Get all tasks for the user from Supabase
    supabase_tasks = await supabase_handler.perform_action(
        APIAction(
            action_type=APIActionType.SUPABASE_LIST_TASKS,
            reason="Fetching tasks for sync",
            parameters={"user_id": user_id}
        )
    )

    stats = {
        "total_tasks": len(supabase_tasks),
        "tasks_synced": 0,
        "tasks_skipped": 0,
        "sync_errors": 0,
        "details": []
    }

    print(f"Found {len(supabase_tasks)} tasks in Supabase")

    # Process each Supabase task
    for task in supabase_tasks:
        task_name = task.get("name", "(Unnamed task)")
        task_id = task.get("id")

        print(f"Processing task: {task_name} (ID: {task_id})")

        meta = task.get("metadata", {}) or {}
        if "gtasks_task_id" in meta and not meta.get("updated_since_sync", False):
            # Already synced (and not updated) -> skip
            stats["tasks_skipped"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "skipped",
                "reason": "Already synced"
            })
            print(f"  - Skipping: Already synced to Google Tasks")
            continue

        try:
            # Prepare fields for Google Tasks creation
            due_date = task.get("due")  # Could be "YYYY-MM-DD" or RFC3339
            description = task.get("description", "")

            create_task_params = {
                "tasklist_id": tasklist_id,
                "title": task_name,
                "notes": description,
            }
            if due_date:
                create_task_params["due"] = due_date

            print(f"  - Creating task in Google Tasks: {task_name}")
            gtask = await gtasks_handler.perform_action(
                APIAction(
                    action_type=APIActionType.TASKS_CREATE_TASK,
                    reason=f"Creating task '{task_name}' in Google Tasks",
                    parameters=create_task_params
                )
            )

            if gtask and "id" in gtask:
                print(f"  - Task created successfully. GTasks ID: {gtask['id']}")
                meta.update({
                    "gtasks_task_id": gtask["id"],
                    "last_synced": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "updated_since_sync": False
                })

                print(f"  - Updating Supabase task with sync metadata")
                await supabase_handler.perform_action(
                    APIAction(
                        action_type=APIActionType.SUPABASE_UPDATE_TASK,
                        reason=f"Updating task '{task_name}' with sync metadata",
                        parameters={
                            "task_id": task_id,
                            "user_id": user_id,
                            "fields_to_update": {"metadata": meta}
                        }
                    )
                )

            stats["tasks_synced"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "synced",
                "gtasks_task_id": gtask.get("id") if gtask else None
            })
            print(f"  - Sync complete for task: {task_name}")

        except Exception as e:
            print(f"  - ERROR syncing task: {str(e)}")
            stats["sync_errors"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "error",
                "error": str(e)
            })

    print("\nTasks Sync Summary:")
    print(f"Total tasks: {stats['total_tasks']}")
    print(f"Synced: {stats['tasks_synced']}")
    print(f"Skipped: {stats['tasks_skipped']}")
    print(f"Errors: {stats['sync_errors']}")

    return stats


async def process_user_id(supabase_handler, user_id):
    """
    Process a user_id by syncing their Supabase calendar and tasks to Google.
    """
    print(f"Processing userId: {user_id}")

    try:
        print(f"\n=== Syncing Supabase Calendar to Google Calendar for user {user_id} ===\n")

        # Get user and check Google credentials
        response = await supabase_handler.client.rpc("get_user", {"user_id_param": user_id}).execute()

        if not response.data:
            print(f"❌ User {user_id} not found in database")
            return

        record = response.data[0]  # Get the user record
        google_credentials = record.get("google_credentials")

        # Check if the user has valid Google credentials
        if not google_credentials or not (
                google_credentials.get("access_token") and
                google_credentials.get("scope") and
                google_credentials.get("refresh_token")):
            print(f"❌ User {user_id} does not have valid Google credentials. Aborting sync.")
            return

        # Create credentials object from stored token information
        authenticated_google_credentials = Credentials(
            token=google_credentials["access_token"],
            refresh_token=google_credentials["refresh_token"],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.getenv('CLIENT_ID'),
            client_secret=os.getenv('CLIENT_SECRET'),
            scopes=google_credentials["scope"].split()
        )

        # 1) Sync to Google Calendar
        print("Initializing Google Calendar handler...")
        async with AsyncGoogleCalendarAPIHandler(authenticated_google_credentials) as gcal_handler:
            # Find/create the target calendar
            calendar_id = await find_or_create_calendar(gcal_handler, DEFAULT_CALENDAR_NAME)

            print(f"\nStarting calendar sync for user_id: {user_id}")
            print(f"Target Google Calendar: {calendar_id}")
            await sync_supabase_to_gcal(
                supabase_handler=supabase_handler,
                gcal_handler=gcal_handler,
                user_id=user_id,
                gcal_id=calendar_id
            )

        # 2) Sync to Google Tasks
        print(f"\n=== Syncing Supabase Tasks to Google Tasks for user {user_id} ===\n")

        async with AsyncGoogleTasksAPIHandler(authenticated_google_credentials) as gtasks_handler:
            # Find/create the target tasklist
            tasklist_id = await find_or_create_tasklist(gtasks_handler, DEFAULT_TASKLIST_NAME)

            print(f"\nStarting tasks sync for user_id: {user_id}")
            print(f"Target Google Tasklist: {tasklist_id}")
            await sync_supabase_to_gtasks(
                supabase_handler=supabase_handler,
                gtasks_handler=gtasks_handler,
                user_id=user_id,
                tasklist_id=tasklist_id
            )

        print("\nAll syncs complete!")

    except Exception as e:
        print(f"Error syncing calendar/tasks for user {user_id}: {str(e)}")


async def handle_broadcast(supabase_handler, payload):
    """
    Handle broadcast messages from Supabase realtime.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        payload: The broadcast payload
    """
    print("\n===== EVENT RECEIVED =====")
    print("Received broadcast event on sync_channel!")
    print("Payload:", payload)
    print("===========================\n")

    if "userId" in payload["payload"]:
        print(f"✅ Processing userId: {payload['payload']['userId']}")
        task = asyncio.create_task(process_user_id(supabase_handler, payload["payload"]["userId"]))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)
    else:
        print("❌ Invalid payload: Missing 'userId'")


async def shutdown(supabase_client, channel):
    """
    Properly shut down the application and cancel all pending tasks.

    Args:
        supabase_client: The Supabase client to close
        channel: The Supabase channel to unsubscribe from
    """
    print("Shutting down...")

    # Cancel all pending tasks
    for task in pending_tasks:
        task.cancel()

    if pending_tasks:
        # Wait for all tasks to complete with a timeout
        await asyncio.wait(pending_tasks, timeout=5)

    # Unsubscribe from the channel
    if channel:
        try:
            await channel.unsubscribe()
            print("Unsubscribed from channel.")
        except Exception as e:
            print(f"Error unsubscribing from channel: {str(e)}")

    # Close or clean up your Supabase client here if needed
    print("Shutdown complete.")


def request_shutdown():
    """
    Signal handler callback to set the shutdown event
    """
    shutdown_event.set()


async def main():
    """
    Main entry point for the application.

    Initializes the Supabase handler, subscribes to the channel,
    and listens for broadcast events. Runs until a shutdown event is triggered.
    """

    # Check required environment variables for Supabase
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("ERROR: Missing required environment variables SUPABASE_URL and/or SUPABASE_KEY")
        print("Please set these environment variables and try again.")
        return 1

    print("\n=== Supabase to Google Calendar/Tasks Sync Listener ===\n")

    # Initialize Supabase handler - do this only once
    supabase_handler = SupabaseCalendarTasksHandler()
    await supabase_handler.init_client()
    supabase_client = supabase_handler.client

    print(f"Connecting to Supabase realtime channel: 'sync'")
    channel = supabase_client.channel("sync")

    def on_status_change(status, error=None):
        if error:
            print(f"❌ Channel error: {error}")
        else:
            print(f"Channel status changed: {status}")
            if status == "SUBSCRIBED":
                print("✅ Successfully subscribed to 'sync'!")
                print("🔍 Listening for 'db-to-google' broadcast events...")

    def on_broadcast(payload):
        task = asyncio.create_task(handle_broadcast(supabase_handler, payload))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    print("Registering 'db-to-google' event handler...")
    channel.on_broadcast(event="db-to-google", callback=on_broadcast)

    print("Subscribing to channel...")
    await channel.subscribe(callback=on_status_change)

    print("\n🚀 LISTENER ACTIVE - Waiting for events on 'sync'")
    print("▶️ Listening for 'db-to-google' broadcast events...")
    print("▶️ Press Ctrl+C to exit (Unix) or close the terminal (Windows).")

    # Keep running until the shutdown_event is set
    while not shutdown_event.is_set():
        await asyncio.sleep(1)

    # Once we're here, we've been asked to shut down
    await shutdown(supabase_client, channel)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Catch KeyboardInterrupt (especially on Windows) and exit gracefully
        print("\nKeyboardInterrupt received. Exiting...")

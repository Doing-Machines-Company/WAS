# db_to_google_test.py

import os
import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import google.auth.transport.requests
from google.oauth2.credentials import Credentials

from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler
from handlers.async_gtasks_handler import AsyncGoogleTasksAPIHandler

from api_agent_classes import APIAction, APIActionType
from handler_parameters.api_actions_params_gcal import (
    CalendarCreateEventParams,
    CalendarListCalendarsParams,
    CalendarCreateCalendarParams
)

# Import the token refresh helper
from google_token_utils import refresh_google_token_if_needed

### No change needed if you'd like same name for both ###
DEFAULT_CALENDAR_NAME = "inbound.fyi"
DEFAULT_TASKLIST_NAME = "inbound.fyi"  # we can reuse or define a new name

# Track tasks so we can clean them up on shutdown
pending_tasks = set()
shutdown_event = asyncio.Event()


async def find_or_create_calendar(gcal_handler, calendar_name: str) -> str:
    print(f"Looking for calendar: '{calendar_name}'...")

    # List existing calendars
    calendars = await gcal_handler.perform_action(
        APIAction(
            action_type=APIActionType.CALENDAR_LIST_CALENDARS,
            reason=f"Looking for calendar '{calendar_name}'",
            parameters=vars(CalendarListCalendarsParams())
        )
    )

    # Check if the calendar already exists
    for calendar in calendars:
        if calendar.get('summary') == calendar_name:
            print(f"Found existing calendar: '{calendar_name}' (ID: {calendar['id']})")
            return calendar['id']

    # Calendar not found; create a new one
    print(f"Calendar '{calendar_name}' not found. Creating new calendar...")
    new_calendar = await gcal_handler.perform_action(
        APIAction(
            action_type=APIActionType.CALENDAR_CREATE_CALENDAR,
            reason=f"Creating calendar '{calendar_name}'",
            parameters=vars(CalendarCreateCalendarParams(summary=calendar_name, timeZone="UTC"))
        )
    )
    print(f"Created calendar: '{calendar_name}' (ID: {new_calendar['id']})")
    return new_calendar['id']


async def find_or_create_tasklist(gtasks_handler, tasklist_name: str) -> str:
    """
    Look for a Google Tasklist named 'tasklist_name'; if not found, create it.
    Returns the tasklist ID.
    """
    print(f"Looking for tasklist: '{tasklist_name}'...")

    # List existing tasklists
    tasklists = await gtasks_handler.perform_action(
        APIAction(
            action_type=APIActionType.TASKS_LIST_TASKLISTS,
            reason=f"Looking for tasklist '{tasklist_name}'",
            parameters={}
        )
    )

    for tl in tasklists:
        if tl.get('title') == tasklist_name:
            print(f"Found existing tasklist: '{tasklist_name}' (ID: {tl['id']})")
            return tl['id']

    # Not found; create a new one
    print(f"Tasklist '{tasklist_name}' not found. Creating new tasklist...")
    new_tl = await gtasks_handler.perform_action(
        APIAction(
            action_type=APIActionType.TASKS_CREATE_TASKLIST,
            reason=f"Creating tasklist '{tasklist_name}'",
            parameters={"title": tasklist_name}
        )
    )
    print(f"Created tasklist: '{tasklist_name}' (ID: {new_tl['id']})")
    return new_tl['id']


async def sync_supabase_to_gcal(
        supabase_handler,
        gcal_handler,
        user_id: str,
        gcal_id: str = 'primary',
        time_zone: str = None
) -> dict:
    """
    Syncs calendar events from Supabase to Google Calendar.
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
        if "gcal_event_id" in event.get("metadata", {}) and not event.get("metadata", {}).get("updated_since_sync", False):
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
            err_str = str(e)
            print(f"  - ERROR syncing event: {err_str}")
            stats["sync_errors"] += 1
            stats["details"].append({
                "event_id": event_id,
                "name": event_name,
                "status": "error",
                "error": err_str
            })
            # Here you could add additional handling for invalid token errors if needed

    print("\nSync Summary:")
    print(f"Total events: {stats['total_events']}")
    print(f"Synced: {stats['events_synced']}")
    print(f"Skipped: {stats['events_skipped']}")
    print(f"Errors: {stats['sync_errors']}")

    return stats


async def sync_supabase_tasks_to_gtasks(
        supabase_handler,
        gtasks_handler,
        user_id: str,
        tasklist_id: str,
        time_zone: str = "America/New_York"
) -> dict:
    """
    Syncs tasks from Supabase to Google Tasks.
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

    for task in supabase_tasks:
        task_name = task.get("name", "(Unnamed task)")
        task_id = task.get("id")

        print(f"Processing task: {task_name} (ID: {task_id})")

        # Skip tasks already synced (and no changes since)
        meta = task.get("metadata", {}) or {}
        if "gtask_id" in meta and not meta.get("updated_since_sync", False):
            stats["tasks_skipped"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "skipped",
                "reason": "Already synced"
            })
            print(f"  - Skipping: Already synced to Google Tasks")
            continue

        # Create the task in Google Tasks
        try:
            due_str = None
            if task.get("due"):
                # Parse the UTC due date string (ensure "Z" is replaced with proper offset)
                utc_due = datetime.fromisoformat(task["due"].replace("Z", "+00:00"))
                # Convert to the user's local timezone
                local_due = utc_due.astimezone(ZoneInfo(time_zone))
                # Zero out the time by setting it to midnight in the local timezone
                local_midnight = local_due.replace(hour=0, minute=0, second=0, microsecond=0)
                # Build a full RFC3339 due string (e.g., "2021-09-30T00:00:00-04:00")
                due_str = local_midnight.isoformat()
                # Extract the local time in 12-hour format with AM/PM for use in the title
                local_time_str = local_due.strftime("%I:%M %p")
                # Append the local time to the task title
                task_name = f"{task_name} (Due {local_time_str})"

            create_params = {
                "tasklist_id": tasklist_id,
                "title": task_name,  # now includes local hour and minutes if due was set
                "notes": task.get("description", ""),
            }
            if due_str:
                create_params["due"] = due_str

            print(f"  - Creating task in Google Tasks: {task_name}")

            gtask = await gtasks_handler.perform_action(
                APIAction(
                    action_type=APIActionType.TASKS_CREATE_TASK,
                    reason=f"Creating task '{task_name}' in Google Tasks",
                    parameters=create_params
                )
            )

            if gtask and "id" in gtask:
                print(f"  - Task created successfully. GTask ID: {gtask['id']}")
                metadata = meta
                metadata.update({
                    "gtask_id": gtask["id"],
                    # 'selfLink' is the direct API link; there's no special "htmlLink" for tasks
                    "gtask_self_link": gtask.get("selfLink", ""),
                    "last_synced": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "updated_since_sync": False
                })

                # Update Supabase with new metadata
                print(f"  - Updating Supabase task with sync metadata")
                await supabase_handler.perform_action(
                    APIAction(
                        action_type=APIActionType.SUPABASE_UPDATE_TASK,
                        reason=f"Updating task '{task_name}' with sync metadata",
                        parameters={
                            "task_id": task_id,
                            "user_id": user_id,
                            "fields_to_update": {"metadata": metadata}
                        }
                    )
                )

            stats["tasks_synced"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "synced",
                "gtask_id": gtask.get("id") if gtask else None
            })
            print(f"  - Sync complete for task: {task_name}")

        except Exception as e:
            err_str = str(e)
            print(f"  - ERROR syncing task: {err_str}")
            stats["sync_errors"] += 1
            stats["details"].append({
                "task_id": task_id,
                "name": task_name,
                "status": "error",
                "error": err_str
            })
            # Here you could add additional handling for invalid token errors if needed

    print("\nTasks Sync Summary:")
    print(f"Total tasks: {stats['total_tasks']}")
    print(f"Synced: {stats['tasks_synced']}")
    print(f"Skipped: {stats['tasks_skipped']}")
    print(f"Errors: {stats['sync_errors']}")

    return stats


async def process_user_id(supabase_handler, user_id):
    """
    Process a user_id by syncing their Supabase calendar to Google Calendar
    AND their tasks to Google Tasks.
    """
    print(f"Processing userId: {user_id}")

    try:
        print(f"\n=== Syncing Supabase Calendar and Tasks to Google for user {user_id} ===\n")

        # Get user and check Google credentials
        response = await supabase_handler.client.rpc("get_user", {"user_id_param": user_id}).execute()
        if not response.data:
            print(f"❌ User {user_id} not found in database")
            return

        record = response.data[0]  # Get the user record
        user_timezone = record.get("timezone", "America/New_York")
        google_credentials = record.get("google_credentials")

        # Check if the user has valid Google credentials
        if not google_credentials or not (
            google_credentials.get("access_token") and
            google_credentials.get("scope") and
            google_credentials.get("refresh_token")
        ):
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

        # Check if the token is expiring soon and refresh if needed using our helper
        await refresh_google_token_if_needed(record, authenticated_google_credentials, google_credentials, supabase_handler, user_id)

        # Initialize Google Calendar and Tasks handlers
        try:
            async with AsyncGoogleCalendarAPIHandler(authenticated_google_credentials) as gcal_handler, \
                    AsyncGoogleTasksAPIHandler(authenticated_google_credentials) as gtasks_handler:

                # First find/create the calendar and tasklist in parallel
                calendar_id, tasklist_id = await asyncio.gather(
                    find_or_create_calendar(gcal_handler, DEFAULT_CALENDAR_NAME),
                    find_or_create_tasklist(gtasks_handler, DEFAULT_TASKLIST_NAME)
                )

                # Then run both syncs in parallel
                calendar_stats, tasks_stats = await asyncio.gather(
                    sync_supabase_to_gcal(
                        supabase_handler=supabase_handler,
                        gcal_handler=gcal_handler,
                        user_id=user_id,
                        gcal_id=calendar_id
                    ),
                    sync_supabase_tasks_to_gtasks(
                        supabase_handler=supabase_handler,
                        gtasks_handler=gtasks_handler,
                        user_id=user_id,
                        tasklist_id=tasklist_id,
                        time_zone=user_timezone
                    )
                )

            print("\nSync complete!")

        except Exception as e:
            err_str = str(e)
            # If an invalid credentials error is detected, force a refresh using our helper
            if "Invalid Credentials" in err_str or "invalid" in err_str.lower():
                print("Detected invalid/expired token error during sync. Attempting to refresh token...")
                await refresh_google_token_if_needed(record, authenticated_google_credentials, google_credentials, supabase_handler, user_id, force_refresh=True)
                print("Database updated with refreshed token. Retrying sync...")

                async with AsyncGoogleCalendarAPIHandler(authenticated_google_credentials) as gcal_handler, \
                        AsyncGoogleTasksAPIHandler(authenticated_google_credentials) as gtasks_handler:
                    calendar_id, tasklist_id = await asyncio.gather(
                        find_or_create_calendar(gcal_handler, DEFAULT_CALENDAR_NAME),
                        find_or_create_tasklist(gtasks_handler, DEFAULT_TASKLIST_NAME)
                    )
                    calendar_stats, tasks_stats = await asyncio.gather(
                        sync_supabase_to_gcal(
                            supabase_handler=supabase_handler,
                            gcal_handler=gcal_handler,
                            user_id=user_id,
                            gcal_id=calendar_id
                        ),
                        sync_supabase_tasks_to_gtasks(
                            supabase_handler=supabase_handler,
                            gtasks_handler=gtasks_handler,
                            user_id=user_id,
                            tasklist_id=tasklist_id,
                            time_zone=user_timezone
                        )
                    )
                print("\nSync complete!")
            else:
                print(f"Error syncing calendar/tasks for user {user_id}: {err_str}")

    except Exception as e:
        print(f"Error processing user {user_id}: {str(e)}")


async def handle_broadcast(supabase_handler, payload):
    """
    Handle broadcast messages from Supabase realtime.
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

    print("Shutdown complete.")


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

    print("\n=== Supabase to Google Calendar & Tasks Sync Listener ===\n")

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
        print("\nKeyboardInterrupt received. Exiting...")

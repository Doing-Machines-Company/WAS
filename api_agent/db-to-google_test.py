import os
import asyncio
import signal
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Import the authentication helper
# from auth_google_calendar_tasks import authenticate
from google.oauth2.credentials import Credentials

# Import the handlers
from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler

# Import action classes
from api_agent_classes import APIAction, APIActionType

# Import parameter classes
from handler_parameters.api_actions_params_gcal import CalendarCreateEventParams, CalendarListCalendarsParams

# Default calendar name
DEFAULT_CALENDAR_NAME = "inbound.fyi"

# Global task list for proper cleanup
pending_tasks = set()


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

    # Track statistics for reporting
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

            # Update Supabase event with Google Calendar event ID if successful
            if gcal_event and "id" in gcal_event:
                print(f"  - Event created successfully. GCal ID: {gcal_event['id']}")

                # Get existing metadata or initialize empty dict
                metadata = event.get("metadata", {}) or {}

                # Update metadata with Google Calendar event ID and sync timestamp
                metadata.update({
                    "gcal_event_id": gcal_event["id"],
                    "gcal_html_link": gcal_event.get("htmlLink", ""),
                    "last_synced": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "updated_since_sync": False
                })

                print(f"  - Updating Supabase event with sync metadata")

                # Update the Supabase event with the new metadata
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
                "gcal_event_id": gcal_event.get("id")
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


async def process_user_id(supabase_handler, user_id):
    """
    Process a user_id by syncing their Supabase calendar to Google Calendar.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        user_id: The ID of the user whose calendar should be synced
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

        # Initialize Google Calendar handler
        print("Initializing Google Calendar handler...")
        async with AsyncGoogleCalendarAPIHandler(authenticated_google_credentials) as gcal_handler:

            # Find or create the target calendar
            calendar_id = await find_or_create_calendar(gcal_handler, DEFAULT_CALENDAR_NAME)

            # Perform the sync
            print(f"\nStarting sync for user_id: {user_id}")
            print(f"Target Google Calendar: {calendar_id}")

            # Run the sync
            await sync_supabase_to_gcal(
                supabase_handler=supabase_handler,
                gcal_handler=gcal_handler,
                user_id=user_id,
                gcal_id=calendar_id
            )

            print("\nSync complete!")

    except Exception as e:
        print(f"Error syncing calendar for user {user_id}: {str(e)}")


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
        # Create a task and add it to our pending tasks set for proper cleanup
        task = asyncio.create_task(process_user_id(supabase_handler, payload["payload"]["userId"]))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)
    else:
        print("❌ Invalid payload: Missing 'userId'")


async def shutdown(supabase_client, channel, loop):
    """
    Properly shut down the application and cancel all pending tasks.

    Args:
        supabase_client: The Supabase client to close
        channel: The Supabase channel to unsubscribe from
        loop: The asyncio event loop
    """
    print("Shutting down...")

    # Cancel all pending tasks
    for task in pending_tasks:
        task.cancel()

    # Wait for all tasks to complete with a timeout
    if pending_tasks:
        await asyncio.wait(pending_tasks, timeout=5)

    # Unsubscribe from the channel
    if channel:
        try:
            await channel.unsubscribe()
            print("Unsubscribed from channel")
        except Exception as e:
            print(f"Error unsubscribing from channel: {str(e)}")

    # Close the Supabase client connection if needed

    # Stop the event loop
    loop.stop()
    print("Shutdown complete")


async def main():
    """
    Main entry point for the application.

    Initializes the Supabase handler, subscribes to the channel,
    and listens for broadcast events.
    """
    # Get the current event loop
    loop = asyncio.get_event_loop()

    # Set up signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(supabase_client, channel, loop)))

    # Check required environment variables for Supabase
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("ERROR: Missing required environment variables SUPABASE_URL and/or SUPABASE_KEY")
        print("Please set these environment variables and try again.")
        return 1

    print("\n=== Supabase to Google Calendar Sync Listener ===\n")

    # Initialize Supabase handler - do this only once
    supabase_handler = SupabaseCalendarTasksHandler()
    await supabase_handler.init_client()

    # Get the async client from the handler
    supabase_client = supabase_handler.client

    # Subscribe to the channel and listen for events
    print(f"Connecting to Supabase realtime channel: 'sync'")
    channel = supabase_client.channel("sync")

    # Define status callback - must be a regular function, not async
    def on_status_change(status, error=None):
        if error:
            print(f"❌ Channel error: {error}")
        else:
            print(f"Channel status changed: {status}")
            if status == "SUBSCRIBED":
                print("✅ Successfully subscribed to 'sync'!")
                print("🔍 Listening for 'db-to-google' broadcast events...")

    # Define broadcast callback - must be a regular function, not async
    def on_broadcast(payload):
        # Create a task and add it to our pending tasks set for proper cleanup
        task = asyncio.create_task(handle_broadcast(supabase_handler, payload))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    # Set up the channel subscription with verbose logging
    print("Registering 'db-to-google' event handler...")
    channel.on_broadcast(event="db-to-google", callback=on_broadcast)

    # Subscribe to the channel with status callback
    print("Subscribing to channel...")
    await channel.subscribe(callback=on_status_change)

    print("\n🚀 LISTENER ACTIVE - Waiting for events on 'sync'")
    print("▶️ Listening for 'db-to-google' broadcast events...")
    print("▶️ Press Ctrl+C to exit.")

    try:
        # Keep the script running indefinitely
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
    finally:
        # If we get here through an exception, ensure we clean up
        await shutdown(supabase_client, channel, loop)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
# supabase_to_google.py

import os
import asyncio
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import dotenv 
# Import the authentication helper
from auth_google_calendar_tasks import authenticate

# Import our API handlers and action classes
from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler
from api_agent_classes import APIAction, APIActionType

# Import parameter classes
from handler_parameters.supabase_calendar_tasks_params import (
    SupabaseListCalendarEventsParams,
    SupabaseCreateCalendarEventParams
)
from handler_parameters.api_actions_params_gcal import CalendarCreateEventParams, CalendarListCalendarsParams

# Default user ID provided
DEFAULT_USER_ID = "28d65756-a289-4a0d-8a97-d5f8e3a3fbc7"
DEFAULT_CALENDAR_NAME = "inbound.fyi"

dotenv.load_dotenv()
async def create_dummy_supabase_event(supabase_handler, user_id: str) -> Dict[str, Any]:
    """
    Create a dummy test event in Supabase calendar with the current timestamp.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        user_id: Supabase user ID to create the event for

    Returns:
        Dict: The created event data
    """
    # Generate a timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate start and end times (start now, end 2 hours later)
    now = datetime.now(timezone.utc)
    start_time = now + timedelta(minutes=30)  # Start 30 minutes from now
    end_time = start_time + timedelta(hours=2)  # End 2 hours after start

    # Format times as ISO strings with Z suffix
    start_iso = start_time.isoformat().replace("+00:00", "Z")
    end_iso = end_time.isoformat().replace("+00:00", "Z")

    print(f"Creating dummy test event in Supabase: 'Test Event - {timestamp}'")

    # Create the event in Supabase
    event_params = SupabaseCreateCalendarEventParams(
        user_id=user_id,
        name=f"Test Event - {timestamp}",
        description=f"This is a test event created by the sync script at {timestamp}",
        start=start_iso,
        end=end_iso,
        metadata={"test_event": True, "created_by": "sync_script"}
    )

    # Create the event using the handler
    created_event = await supabase_handler.perform_action(
        APIAction(
            action_type=APIActionType.SUPABASE_CREATE_CALENDAR_EVENT,
            reason="Creating test event for sync",
            parameters=vars(event_params)
        )
    )

    print(f"Dummy event created successfully with ID: {created_event['id']}")
    return created_event


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

    # Calendar not found, create it
    print(f"Calendar '{calendar_name}' not found. Creating...")

    # Create a new calendar
    # Note: The Google Calendar API doesn't have a direct "create calendar" endpoint in the provided handler
    # We would need to extend the handler with that functionality
    print(f"Sorry, automatic calendar creation is not implemented in the current handler.")
    print(f"Please create the calendar '{calendar_name}' manually in Google Calendar.")

    # Use primary calendar as fallback
    print(f"Using 'primary' calendar as fallback.")
    return 'primary'


async def sync_supabase_to_gcal(
        supabase_handler,
        gcal_handler,
        user_id: str,
        gcal_id: Optional[str] = 'primary',
        only_future_events: bool = True,
        add_sync_metadata: bool = True,
        time_zone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Syncs calendar events from Supabase to Google Calendar.

    Args:
        supabase_handler: Instance of SupabaseCalendarTasksHandler
        gcal_handler: Instance of AsyncGoogleCalendarAPIHandler
        user_id: Supabase user ID to filter events by
        gcal_id: Google Calendar ID to add events to (default: 'primary')
        only_future_events: Only sync events that haven't ended yet
        add_sync_metadata: Add sync metadata to Supabase events
        time_zone: Time zone to use for events (default: None)

    Returns:
        Dictionary with sync statistics
    """
    # Initialize the supabase client if it hasn't been initialized
    if supabase_handler.client is None:
        await supabase_handler.init_client()

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
            if add_sync_metadata and gcal_event and "id" in gcal_event:
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


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Sync Supabase calendar events to Google Calendar")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID,
                        help=f"Supabase user ID to sync events for (default: {DEFAULT_USER_ID})")
    parser.add_argument("--calendar-name", default=DEFAULT_CALENDAR_NAME,
                        help=f"Name of the Google Calendar to use (default: {DEFAULT_CALENDAR_NAME})")
    parser.add_argument("--timezone", default=None, help="Timezone for events (e.g., 'America/New_York')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually create events, just print what would happen")
    parser.add_argument("--no-dummy-event", action="store_true", help="Skip creating a dummy test event")
    args = parser.parse_args()

    # Check required environment variables for Supabase
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("ERROR: Missing required environment variables SUPABASE_URL and/or SUPABASE_KEY")
        print("Please set these environment variables and try again.")
        return 1

    print("\n=== Supabase to Google Calendar Sync ===\n")

    # 1. Authenticate with Google Calendar API
    print("Authenticating with Google Calendar API...")
    credentials = authenticate()

    # 2. Initialize Supabase handler
    print("Initializing Supabase handler...")
    supabase_handler = SupabaseCalendarTasksHandler()
    await supabase_handler.init_client()

    # 3. Create a dummy test event (unless --no-dummy-event is specified)
    if not args.no_dummy_event:
        await create_dummy_supabase_event(supabase_handler, args.user_id)
    else:
        print("Skipping dummy event creation (--no-dummy-event specified)")

    # 4. Initialize Google Calendar handler using async context manager
    print("Initializing Google Calendar handler...")
    async with AsyncGoogleCalendarAPIHandler(credentials) as gcal_handler:

        # 5. Find or create the target calendar
        calendar_id = await find_or_create_calendar(gcal_handler, args.calendar_name)

        # 6. Perform the sync
        print(f"\nStarting sync for user_id: {args.user_id}")
        print(f"Target Google Calendar: {calendar_id}")
        print(f"Timezone: {args.timezone or 'Default'}")

        if args.dry_run:
            print("\nDRY RUN MODE - No events will actually be created")
            # You could implement a dry run version of the function here
            print("Dry run not implemented yet")
            return 0

        # Run the sync
        results = await sync_supabase_to_gcal(
            supabase_handler=supabase_handler,
            gcal_handler=gcal_handler,
            user_id=args.user_id,
            gcal_id=calendar_id,
            time_zone=args.timezone
        )

        print("\nSync complete!")

    return 0


if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    exit(exit_code)
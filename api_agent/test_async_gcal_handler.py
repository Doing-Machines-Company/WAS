# test_async_gcal_handler.py
import asyncio
import os
import pickle
import datetime
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from api_agent_classes import APIAction, APIActionType
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler
from handler_parameters.api_actions_params_gcal import (
    CalendarListCalendarsParams,
    CalendarCreateEventParams,
    CalendarListEventsParams,
    CalendarUpdateEventParams,
    CalendarDeleteEventParams,
    CalendarMoveEventParams
)


def load_credentials():
    """Load and refresh Google API credentials"""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save the refreshed token
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        else:
            raise Exception("No valid credentials found. Run authentication script first.")

    return creds


async def test_list_calendars():
    """Test listing calendars"""
    creds = load_credentials()

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.CALENDAR_LIST_CALENDARS,
            parameters={}
        )

        print("\n===== Testing List Calendars =====")
        calendars = await handler.perform_action(action)
        print(f"Found {len(calendars)} calendars:")
        for calendar in calendars:
            print(f"  - {calendar.get('summary')} ({calendar.get('id')})")

        return calendars


async def test_list_events(calendar_id=None):
    """Test listing events from a calendar"""
    creds = load_credentials()

    # Get events from the last 7 days
    now = datetime.datetime.utcnow()
    seven_days_ago = now - datetime.timedelta(days=7)

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.CALENDAR_LIST_EVENTS,
            parameters={
                "calendarId": calendar_id or "primary",
                "timeMin": seven_days_ago.isoformat() + "Z",
                "timeMax": now.isoformat() + "Z",
                "maxResults": 10
            }
        )

        print(f"\n===== Testing List Events (Calendar: {calendar_id or 'primary'}) =====")
        events = await handler.perform_action(action)

        print(f"Found {len(events)} events in the past 7 days:")
        for event in events:
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'Unknown'))
            print(f"  - {event.get('summary')} (starts: {start})")

        return events


async def test_create_event(calendar_id=None):
    """Test creating a new event"""
    creds = load_credentials()

    # Create an event for tomorrow
    tomorrow = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    tomorrow_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.CALENDAR_CREATE_EVENT,
            parameters={
                "calendarId": calendar_id or "primary",
                "summary": "Test Event from Async Handler",
                "description": "This is a test event created by the async handler",
                "location": "Virtual",
                "start": tomorrow_start.isoformat(),
                "end": tomorrow_end.isoformat(),
                "timeZone": "UTC"
            }
        )

        print(f"\n===== Testing Create Event (Calendar: {calendar_id or 'primary'}) =====")
        event = await handler.perform_action(action)
        print(f"Created event:")
        print(f"  - ID: {event.get('id')}")
        print(f"  - Summary: {event.get('summary')}")
        print(f"  - Start: {event.get('start', {}).get('dateTime')}")

        return event


async def test_update_event(event_id, calendar_id=None):
    """Test updating an existing event"""
    creds = load_credentials()

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        # Fields to update
        fields_to_update = {
            "summary": "Updated Test Event",
            "description": "This event was updated by the async handler"
        }

        action = APIAction(
            action_type=APIActionType.CALENDAR_UPDATE_EVENT,
            parameters={
                "calendarId": calendar_id or "primary",
                "event_id": event_id,
                "fields_to_update": fields_to_update
            }
        )

        print(f"\n===== Testing Update Event (ID: {event_id}) =====")
        updated_event = await handler.perform_action(action)
        print(f"Updated event:")
        print(f"  - ID: {updated_event.get('id')}")
        print(f"  - New Summary: {updated_event.get('summary')}")
        print(f"  - New Description: {updated_event.get('description')}")

        return updated_event


async def test_reschedule_event(event_id, calendar_id=None):
    """Test rescheduling an event to the next day"""
    creds = load_credentials()

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        # First, get the current event to access its times
        get_action = APIAction(
            action_type=APIActionType.CALENDAR_LIST_EVENTS,
            parameters={
                "calendarId": calendar_id or "primary",
                "maxResults": 1
            }
        )

        # Get the event details first
        original_event = await handler.get_event(calendar_id or "primary", event_id)

        # Extract the current start and end times
        start_obj = original_event.get('start', {})
        end_obj = original_event.get('end', {})

        # Determine if it's an all-day event or a timed event
        is_all_day = 'date' in start_obj

        if is_all_day:
            # For all-day events, just add a day to the date strings
            start_date = datetime.datetime.strptime(start_obj['date'], "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_obj['date'], "%Y-%m-%d").date()

            # Add one day
            new_start_date = (start_date + datetime.timedelta(days=1)).isoformat()
            new_end_date = (end_date + datetime.timedelta(days=1)).isoformat()

            # Create the updated event objects
            new_start = {"date": new_start_date}
            new_end = {"date": new_end_date}

        else:
            # For timed events, parse the datetime and add a day
            start_time = datetime.datetime.fromisoformat(start_obj['dateTime'].replace('Z', '+00:00'))
            end_time = datetime.datetime.fromisoformat(end_obj['dateTime'].replace('Z', '+00:00'))

            # Add one day
            new_start_time = (start_time + datetime.timedelta(days=1))
            new_end_time = (end_time + datetime.timedelta(days=1))

            # Format as ISO string
            new_start_iso = new_start_time.isoformat().replace('+00:00', 'Z')
            new_end_iso = new_end_time.isoformat().replace('+00:00', 'Z')

            # Create the updated event objects
            new_start = {"dateTime": new_start_iso}
            new_end = {"dateTime": new_end_iso}

            # Preserve timezone if it exists
            if 'timeZone' in start_obj:
                new_start['timeZone'] = start_obj['timeZone']
            if 'timeZone' in end_obj:
                new_end['timeZone'] = end_obj['timeZone']

        # Fields to update
        fields_to_update = {
            "summary": original_event.get('summary', '') + " (Rescheduled)",
            "start": new_start,
            "end": new_end
        }

        # Create update action
        action = APIAction(
            action_type=APIActionType.CALENDAR_UPDATE_EVENT,
            parameters={
                "calendarId": calendar_id or "primary",
                "event_id": event_id,
                "fields_to_update": fields_to_update
            }
        )

        print(f"\n===== Testing Reschedule Event (ID: {event_id}) =====")
        updated_event = await handler.perform_action(action)

        # Extract the new start time for display
        if is_all_day:
            new_start_display = updated_event.get('start', {}).get('date', 'Unknown')
        else:
            new_start_display = updated_event.get('start', {}).get('dateTime', 'Unknown')

        print(f"Rescheduled event:")
        print(f"  - ID: {updated_event.get('id')}")
        print(f"  - Summary: {updated_event.get('summary')}")
        print(f"  - New Start Time: {new_start_display}")

        return updated_event


async def test_delete_event(event_id, calendar_id=None):
    """Test deleting an event"""
    creds = load_credentials()

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.CALENDAR_DELETE_EVENT,
            parameters={
                "calendarId": calendar_id or "primary",
                "event_id": event_id
            }
        )

        print(f"\n===== Testing Delete Event (ID: {event_id}) =====")
        result = await handler.perform_action(action)
        print(f"Delete result: {result}")

        return result


async def test_parallel_requests():
    """Test executing multiple requests in parallel"""
    creds = load_credentials()

    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        # Create multiple API action tasks
        print("\n===== Testing Parallel Requests =====")
        print("Starting parallel requests...")

        start_time = datetime.datetime.now()

        # Create tasks for parallel execution
        tasks = [
            # List calendars
            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_CALENDARS,
                parameters={}
            )),

            # List events from primary calendar
            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_EVENTS,
                parameters={"maxResults": 10}
            )),

            # List events from primary calendar with different parameters
            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_EVENTS,
                parameters={
                    "timeMin": (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat() + "Z",
                    "maxResults": 5
                }
            ))
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks)

        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # Process results
        calendars, recent_events, month_events = results

        print(f"Parallel requests completed in {execution_time:.2f} seconds")
        print(f"Found {len(calendars)} calendars")
        print(f"Found {len(recent_events)} recent events")
        print(f"Found {len(month_events)} events in the last month")

        return results


async def run_all_tests():
    """Run all tests in a logical sequence"""
    try:
        # List calendars
        calendars = await test_list_calendars()

        # List events
        events = await test_list_events()

        # Create an event
        new_event = await test_create_event()
        event_id = new_event.get('id')

        # Wait a moment to ensure the event is fully processed
        await asyncio.sleep(2)

        # Update the event
        if event_id:
            updated_event = await test_update_event(event_id)

            # Wait a moment to ensure the update is processed
            await asyncio.sleep(2)

            # Reschedule the event to the next day
            rescheduled_event = await test_reschedule_event(event_id)

            # Wait a moment to ensure the reschedule is processed
            await asyncio.sleep(2)

            # Delete the event
            await test_delete_event(event_id)

        # Run parallel request test
        await test_parallel_requests()

        print("\n===== All tests completed successfully =====")

    except Exception as e:
        print(f"\nError during tests: {e}")


# Comparison test to show performance difference
async def comparison_test():
    """Compare performance of sequential vs parallel requests"""
    creds = load_credentials()

    print("\n===== Performance Comparison: Sequential vs Parallel =====")

    # Test sequential execution
    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        print("Running sequential requests...")
        sequential_start = datetime.datetime.now()

        # Run requests one after another
        calendars = await handler.perform_action(APIAction(
            action_type=APIActionType.CALENDAR_LIST_CALENDARS,
            parameters={}
        ))

        recent_events = await handler.perform_action(APIAction(
            action_type=APIActionType.CALENDAR_LIST_EVENTS,
            parameters={"maxResults": 10}
        ))

        month_events = await handler.perform_action(APIAction(
            action_type=APIActionType.CALENDAR_LIST_EVENTS,
            parameters={
                "timeMin": (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat() + "Z",
                "maxResults": 5
            }
        ))

        sequential_end = datetime.datetime.now()
        sequential_time = (sequential_end - sequential_start).total_seconds()

        print(f"Sequential execution completed in {sequential_time:.2f} seconds")

    # Test parallel execution
    async with AsyncGoogleCalendarAPIHandler(creds) as handler:
        print("Running parallel requests...")
        parallel_start = datetime.datetime.now()

        # Create tasks for parallel execution
        tasks = [
            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_CALENDARS,
                parameters={}
            )),

            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_EVENTS,
                parameters={"maxResults": 10}
            )),

            handler.perform_action(APIAction(
                action_type=APIActionType.CALENDAR_LIST_EVENTS,
                parameters={
                    "timeMin": (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat() + "Z",
                    "maxResults": 5
                }
            ))
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks)

        parallel_end = datetime.datetime.now()
        parallel_time = (parallel_end - parallel_start).total_seconds()

        print(f"Parallel execution completed in {parallel_time:.2f} seconds")

    # Calculate and display improvement
    if sequential_time > 0:
        improvement = (sequential_time - parallel_time) / sequential_time * 100
        print(f"Parallel execution was {improvement:.2f}% faster")

    return {
        "sequential_time": sequential_time,
        "parallel_time": parallel_time
    }


if __name__ == "__main__":
    # Run all individual tests
    # asyncio.run(run_all_tests())

    # Or just run the performance comparison
    # asyncio.run(comparison_test())

    # Or run a specific test
    # asyncio.run(test_list_calendars())
    # asyncio.run(test_list_events())
    # asyncio.run(test_create_event())
    # asyncio.run(test_parallel_requests())

    # Test the reschedule functionality (create event then reschedule it)
    async def test_create_and_reschedule():
        new_event = await test_create_event()
        event_id = new_event.get('id')
        await asyncio.sleep(2)  # Wait for creation to process
        if event_id:
            await test_reschedule_event(event_id)
    asyncio.run(test_create_and_reschedule())
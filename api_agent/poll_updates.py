# test_canvas_gcal_gtasks_agent.py
import os
import asyncio
import logging
import dotenv
import supabase
from datetime import datetime, timezone
from agents.canvas.canvas_api_agent import CanvasAPIAgent
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent
from agents.gradescope.gradescope_api_agent import GradescopeAPIAgent
from agents.supabase_cal_task.supabase_calendar_tasks_api_agent_multi import SupabaseCalendarTasksAPIAgentMulti
from google.oauth2.credentials import Credentials
import aiohttp

# Import sync functions (for backwards compatibility, these may still be used elsewhere)
from google_sync_utils import (
    find_or_create_calendar,
    find_or_create_tasklist,
    sync_supabase_to_gcal,
    sync_supabase_tasks_to_gtasks
)

# Initialize Supabase handler and async Google handlers
from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler
from handlers.async_gtasks_handler import AsyncGoogleTasksAPIHandler

# Default calendar and tasklist names
DEFAULT_CALENDAR_NAME = "inbound.fyi"
DEFAULT_TASKLIST_NAME = "inbound.fyi"

logging.basicConfig(level=logging.INFO)

"""
import asyncio
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I have a birthday for James Chan on Feb 10."
    )
    asyncio.run(agent.run())
"""

dotenv.load_dotenv()


async def run_gradescope_agent(credentials):
    """Run the Gradescope agent with the provided credentials."""
    try:
        if credentials and credentials.get('email') and credentials.get('password'):
            gradescope_agent = GradescopeAPIAgent(credentials=credentials)
            print("Agent task:", gradescope_agent.task)
            await gradescope_agent.run()
            print("Agent run has completed.")
            poll_output = gradescope_agent.get_poll_output()
            return poll_output
    except Exception as e:
        print("Error running gradescope agent", e)
    return []


async def run_canvas_agent(domain, token, session):
    """Run the Canvas agent with the provided domain and token."""
    try:
        if domain and token:
            canvas_agent = CanvasAPIAgent(
                credentials={'url': 'https://' + domain, 'token': token},
                session=session
            )
            print("Agent task:", canvas_agent.task)
            await canvas_agent.run()
            print("Agent run has completed.")
            poll_output = canvas_agent.get_poll_output()
            return poll_output
    except Exception as e:
        print("Error running canvas agent", e)
    return []


async def run_supabase_agent(task_string, user_id):
    """Run the Supabase Calendar Tasks agent."""
    try:
        supabase_agent = SupabaseCalendarTasksAPIAgentMulti(
            task=task_string,
            user_id=user_id
        )
        await supabase_agent.run()
    except Exception as e:
        print("Error running supabase agent", e)


async def process_polls(poll_data, user_id, step_size=1):
    """Process poll outputs and run the Supabase agent in parallel."""
    tasks = []
    for i in range(0, len(poll_data), step_size):
        cur_chunk = poll_data[i:i + step_size]
        task_string = ""
        for j, linmem in enumerate(cur_chunk):
            task_string += f"{j})\nCall: \n{linmem.call}\nReceived: \n{linmem.received}\n"
        tasks.append(run_supabase_agent(task_string, user_id))

    await asyncio.gather(*tasks)


async def process_user(record):
    """Process a single user's operations sequentially."""
    try:
        google_credentials = record.get("google_credentials")
        gradescope_credentials = record.get("gradescope_credentials")
        canvas_token = record.get("canvas_token")
        canvas_domain = record.get("canvas_domain")
        # Optionally, if you only need the canvas token string:
        canvas_token_str = canvas_token.get("token") if canvas_token else None

        print("Processing user:", record.get("email"))

        # Run Gradescope agent
        poll_out_gradescope = await run_gradescope_agent(gradescope_credentials)
        await process_polls(poll_out_gradescope, record["user_id"])

        # Run Canvas agent (canvas_session is accessed from the global scope)
        poll_out_canvas = await run_canvas_agent(canvas_domain, canvas_token_str, canvas_session)
        await process_polls(poll_out_canvas, record["user_id"])

        # Sync Supabase calendar and tasks to Google using sync_with_google_credentials
        if (google_credentials and google_credentials.get("access_token") and
                google_credentials.get("refresh_token") and google_credentials.get("scope")):
            print(f"\n=== Syncing Supabase Calendar and Tasks to Google for user {record['user_id']} ===\n")

            authenticated_google_credentials = Credentials(
                token=google_credentials["access_token"],
                refresh_token=google_credentials["refresh_token"],
                token_uri='https://oauth2.googleapis.com/token',
                client_id=os.getenv('CLIENT_ID'),
                client_secret=os.getenv('CLIENT_SECRET'),
                scopes=google_credentials["scope"].split()
            )

            # Initialize the Supabase handler
            supabase_handler = SupabaseCalendarTasksHandler()
            await supabase_handler.init_client()

            user_timezone = record.get("timezone", "America/New_York")

            # Use sync_with_google_credentials instead of manually handling the sync
            from google_sync_utils import sync_with_google_credentials
            await sync_with_google_credentials(
                supabase_handler,
                record["user_id"],
                record,
                user_timezone,
                authenticated_google_credentials,
                google_credentials
            )

        print("\nSync complete!")
    except Exception as e:
        print(f"Error processing user {record.get('email')}: {e}")


async def main():
    global canvas_session

    valid_emails = {'cadatepe@andrew.cmu.edu', 'jamesc3@andrew.cmu.edu'}
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)
    canvas_session = aiohttp.ClientSession()
    users = client.rpc("get_users").execute()

    if users.data:
        # Filter valid users
        valid_users = [record for record in users.data if record.get("email") in valid_emails]

        # Process all users in parallel
        await asyncio.gather(*[process_user(record) for record in valid_users])

    await canvas_session.close()


# Global canvas_session that will be shared across all users
canvas_session = None

if __name__ == "__main__":
    asyncio.run(main())

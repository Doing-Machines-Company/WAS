# poll_updates.py
import os
import asyncio
import logging
import dotenv
import supabase
import concurrent.futures
import threading
from datetime import datetime, timezone
from agents.canvas.canvas_api_agent import CanvasAPIAgent
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent
from agents.gradescope.gradescope_api_agent import GradescopeAPIAgent
from agents.supabase_cal_task.supabase_calendar_tasks_api_agent_multi import SupabaseCalendarTasksAPIAgentMulti
from google.oauth2.credentials import Credentials
from supabase._async.client import create_client

import time 
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

# Configure logging with thread information
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()


async def run_gradescope_agent(credentials):
    """Run the Gradescope agent deterministically without LLM involvement."""
    try:
        if credentials and credentials.get('email') and credentials.get('password'):
            gradescope_agent = GradescopeAPIAgent(credentials=credentials)
            logger.info("Running Gradescope agent deterministically")
            poll_output = await gradescope_agent.get_all_assignments_deterministic()
            await gradescope_agent.cleanup()
            return poll_output
    except Exception as e:
        logger.error(f"Error running gradescope agent: {e}")
    return []


async def run_canvas_agent(domain, token, session):
    """Run the Canvas agent deterministically without LLM involvement."""
    try:
        if domain and token:
            canvas_agent = CanvasAPIAgent(
                credentials={'url': 'https://' + domain, 'token': token},
                session=session
            )
            logger.info("Running Canvas agent deterministically")
            poll_output = await canvas_agent.get_all_assignments_deterministic()
            return poll_output
    except Exception as e:
        logger.error(f"Error running canvas agent: {e}")
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
        logger.error(f"Error running supabase agent: {e}")


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


async def process_user(record, session_for_thread):
    """Process a single user's operations sequentially."""
    try:
        google_credentials = record.get("google_credentials")
        gradescope_credentials = record.get("gradescope_credentials")
        canvas_token = record.get("canvas_token")
        canvas_domain = record.get("canvas_domain")
        # Optionally, if you only need the canvas token string:
        canvas_token_str = canvas_token.get("token") if canvas_token else None

        logger.info(f"Processing user: {record.get('email')} (Thread: {threading.current_thread().name})")

        # Run Gradescope agent
        poll_out_gradescope = await run_gradescope_agent(gradescope_credentials)
        input(poll_out_gradescope)
        await process_polls(poll_out_gradescope, record["user_id"])

        # Run Canvas agent (use the thread's session)
        poll_out_canvas = await run_canvas_agent(canvas_domain, canvas_token_str, session_for_thread)
        await process_polls(poll_out_canvas, record["user_id"])

        # Sync Supabase calendar and tasks to Google using sync_with_google_credentials
        # if (google_credentials and google_credentials.get("access_token") and
        #         google_credentials.get("refresh_token") and google_credentials.get("scope")):
        #     logger.info(f"Syncing Supabase Calendar and Tasks to Google for user {record['user_id']}")

        #     authenticated_google_credentials = Credentials(
        #         token=google_credentials["access_token"],
        #         refresh_token=google_credentials["refresh_token"],
        #         token_uri='https://oauth2.googleapis.com/token',
        #         client_id=os.getenv('CLIENT_ID'),
        #         client_secret=os.getenv('CLIENT_SECRET'),
        #         scopes=google_credentials["scope"].split()
        #     )

        #     # Initialize the Supabase handler
        #     supabase_handler = SupabaseCalendarTasksHandler()
        #     await supabase_handler.init_client()

        #     user_timezone = record.get("timezone", "America/New_York")

        #     # Use sync_with_google_credentials instead of manually handling the sync
        #     from google_sync_utils import sync_with_google_credentials
        #     await sync_with_google_credentials(
        #         supabase_handler,
        #         record["user_id"],
        #         record,
        #         user_timezone,
        #         authenticated_google_credentials,
        #         google_credentials
        #     )

        # Update last_synced timestamp
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        async_client = await create_client(url, key)
        
        current_time = datetime.now(timezone.utc).isoformat()
        await async_client.table("users").update({"last_synced": current_time}).eq("user_id", record["user_id"]).execute()
        
        logger.info(f"Sync complete for user: {record.get('email')}")
    except Exception as e:
        logger.error(f"Error processing user {record.get('email')}: {e}")


def process_user_batch(user_batch):
    """Process a batch of users in a separate thread."""
    thread_name = threading.current_thread().name
    logger.info(f"Starting thread {thread_name} with {len(user_batch)} users")
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Create a session for this thread
        session_for_thread = None
        
        async def init_and_process():
            nonlocal session_for_thread
            # Create aiohttp session for this thread
            session_for_thread = aiohttp.ClientSession()
            # Process all users in this batch concurrently
            await asyncio.gather(*[process_user(record, session_for_thread) for record in user_batch])
            # Close the session
            await session_for_thread.close()
            
        # Run the async tasks in this thread's event loop
        loop.run_until_complete(init_and_process())
        
    except Exception as e:
        logger.error(f"Error in thread {thread_name}: {e}")
    finally:
        loop.close()
        logger.info(f"Thread {thread_name} completed")


def main_threaded():
    """Main function that distributes user processing across threads."""
    logger.info("Starting multi-threaded processing")
    
    # valid_emails = {'cadatepe@andrew.cmu.edu', 'jamesc3@andrew.cmu.edu'}
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)
    
    # Get users synchronously
    users = client.rpc("get_users").execute()
    
    if not users.data:
        logger.info("No users found")
        return
    
    # Filter valid users
    valid_users = [record for record in users.data]
    
    if not valid_users:
        logger.info("No valid users found")
        return
    
    # Determine batch size and number of threads
    num_users = len(valid_users)
    num_threads = min(num_users, os.cpu_count() or 4)  # Use at most number of CPUs
    batch_size = max(1, (num_users + num_threads - 1) // num_threads)  # Ceiling division
    
    logger.info(f"Processing {num_users} users with {num_threads} threads (batch size ~{batch_size})")
    
    # Create batches
    user_batches = [valid_users[i:i+batch_size] for i in range(0, num_users, batch_size)]
    
    # Process batches in thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(process_user_batch, batch) for batch in user_batches]
        
        # Wait for all futures to complete
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # This will re-raise any exceptions that occurred in the thread
            except Exception as e:
                logger.error(f"Thread execution failed: {e}")
    
    logger.info("All processing complete")


# Keep the async version for backwards compatibility
async def main():
    """Original async version - kept for backwards compatibility."""
    logger.warning("Using deprecated single-threaded mode. Consider using main_threaded() instead.")
    start = time.time()
    # Create a shared aiohttp session
    global canvas_session
    canvas_session = aiohttp.ClientSession()
    
    valid_emails = {'cadatepe@andrew.cmu.edu'}
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)
    users = client.rpc("get_users").execute()
    
    if users.data:
        valid_users = [record for record in users.data if record.get('email') in valid_emails]
        # Filter valid users
        input(valid_users)
        # Process all users in parallel
        await asyncio.gather(*[process_user(record, canvas_session) for record in valid_users])

    await canvas_session.close()
    print("Syncing ", len(valid_users), " took ", time.time() - start)

# Global canvas_session that will be used in the original async mode
canvas_session = None

if __name__ == "__main__":
    # Use the threaded version
    asyncio.run(main())

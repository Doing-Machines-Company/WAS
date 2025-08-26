import os
import argparse
import asyncio
import json
import time
import logging
import dotenv
import supabase
from typing import List, Optional, Set
from google.oauth2.credentials import Credentials

from handlers.async_gcal_handler import AsyncGoogleCalendarAPIHandler
from handlers.async_gtasks_handler import AsyncGoogleTasksAPIHandler
from google_sync_utils import delete_inbound_calendar_and_tasks
from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler
from google_token_utils import refresh_google_token_if_needed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv()


async def delete_user_inbound_data(
    record: dict,
    supabase_handler,
    dry_run: bool = False
) -> dict:
    """
    Delete all events and tasks from inbound.fyi calendar and tasklist for a single user.
    
    Args:
        record: User record from Supabase
        supabase_handler: Initialized Supabase handler
        dry_run: If True, don't actually delete anything, just show what would be deleted
        
    Returns:
        Dict with summary of deleted items
    """
    user_id = record.get("user_id")
    email = record.get("email")
    
    result = {
        "email": email,
        "user_id": user_id,
        "success": False,
        "error": None,
        "deleted_events": 0,
        "deleted_tasks": 0,
        "dry_run": dry_run
    }
    
    try:
        google_credentials = record.get("google_credentials")
        
        if not google_credentials or not (
            google_credentials.get("access_token") and
            google_credentials.get("refresh_token") and
            google_credentials.get("scope")
        ):
            logger.warning(f"User {email} does not have valid Google credentials. Skipping.")
            result["error"] = "Missing valid Google credentials"
            return result
        
        # Initialize Google credentials
        authenticated_google_credentials = Credentials(
            token=google_credentials["access_token"],
            refresh_token=google_credentials["refresh_token"],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.getenv('CLIENT_ID'),
            client_secret=os.getenv('CLIENT_SECRET'),
            scopes=google_credentials["scope"].split()
        )
        
        # Ensure token is up-to-date
        await refresh_google_token_if_needed(record, authenticated_google_credentials, google_credentials, supabase_handler, user_id)
        
        if dry_run:
            logger.info(f"DRY RUN: Would delete all inbound.fyi events and tasks for {email}")
            result["success"] = True
            return result
            
        # Process the deletion
        async with AsyncGoogleCalendarAPIHandler(authenticated_google_credentials) as gcal_handler, \
                  AsyncGoogleTasksAPIHandler(authenticated_google_credentials) as gtasks_handler:
            
            deletion_result = await delete_inbound_calendar_and_tasks(gcal_handler, gtasks_handler)
            
            result["deleted_events"] = deletion_result["deleted_events"]
            result["deleted_tasks"] = deletion_result["deleted_tasks"]
            result["success"] = True
            
        logger.info(f"Deleted {result['deleted_events']} events and {result['deleted_tasks']} tasks for {email}")
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing {email}: {error_message}")
        result["error"] = error_message
        
    return result


async def batch_delete_user_data(
    valid_emails: Optional[Set[str]] = None,
    dry_run: bool = False,
    max_concurrent: int = 5
) -> dict:
    """
    Delete all events and tasks from inbound.fyi calendar and tasklist for multiple users.
    
    Args:
        valid_emails: Optional set of emails to process (if None, process all)
        dry_run: If True, don't actually delete anything, just show what would be deleted
        max_concurrent: Maximum number of concurrent deletions
        
    Returns:
        Dict with summary of operations
    """
    # Initialize Supabase client
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)
    
    # Get users from Supabase
    users_response = client.rpc("get_users").execute()
    users = users_response.data or []
    
    total_users = len(users)
    if total_users == 0:
        logger.warning("No users found in database")
        return {"error": "No users found"}
    
    # Filter by valid_emails if provided
    filtered_users = users
    if valid_emails:
        filtered_users = [user for user in users if user.get('email') in valid_emails]
        skipped_count = total_users - len(filtered_users)
        logger.info(f"Filtered to {len(filtered_users)} users (skipped {skipped_count})")
    
    # Initialize Supabase handler for token refresh
    supabase_handler = SupabaseCalendarTasksHandler()
    await supabase_handler.init_client()
    
    results = {
        "total_users": len(filtered_users),
        "processed_users": 0,
        "successful_deletions": 0,
        "failed_deletions": 0,
        "total_events_deleted": 0,
        "total_tasks_deleted": 0,
        "details": []
    }
    
    # Process users in batches to limit concurrency
    for i in range(0, len(filtered_users), max_concurrent):
        batch = filtered_users[i:i+max_concurrent]
        
        # Process batch concurrently
        batch_tasks = [delete_user_inbound_data(record, supabase_handler, dry_run) for record in batch]
        batch_results = await asyncio.gather(*batch_tasks)
        
        # Update stats
        for result in batch_results:
            results["processed_users"] += 1
            results["details"].append(result)
            
            if result["success"]:
                results["successful_deletions"] += 1
                if not dry_run:
                    results["total_events_deleted"] += result["deleted_events"]
                    results["total_tasks_deleted"] += result["deleted_tasks"]
            else:
                results["failed_deletions"] += 1
                
        logger.info(f"Processed {min(i+max_concurrent, len(filtered_users))}/{len(filtered_users)} users")
    
    return results


async def main():
    parser = argparse.ArgumentParser(description="Delete all inbound.fyi calendar events and tasks for specified users")
    parser.add_argument("--valid-emails", type=str, help="Comma-separated list of emails to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually delete anything, just show what would be deleted")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Maximum number of concurrent deletions")
    
    args = parser.parse_args()
    
    valid_emails_set = None
    if args.valid_emails:
        valid_emails_set = {email.strip() for email in args.valid_emails.split(",")}
        logger.info(f"Filtering to emails: {valid_emails_set}")
    
    start_time = time.time()
    
    results = await batch_delete_user_data(
        valid_emails=valid_emails_set,
        dry_run=args.dry_run,
        max_concurrent=args.max_concurrent
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    results["duration_seconds"] = duration
    
    logger.info("\nSummary:")
    logger.info(f"Total users: {results['total_users']}")
    logger.info(f"Processed users: {results['processed_users']}")
    logger.info(f"Successful deletions: {results['successful_deletions']}")
    logger.info(f"Failed deletions: {results['failed_deletions']}")
    if not args.dry_run:
        logger.info(f"Total events deleted: {results['total_events_deleted']}")
        logger.info(f"Total tasks deleted: {results['total_tasks_deleted']}")
    logger.info(f"Total time: {duration:.2f} seconds")
    
    # Save detailed results to a JSON file
    result_file = "deletion_results.json"
    with open(result_file, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"\nDetailed results saved to {result_file}")


if __name__ == "__main__":
    asyncio.run(main())
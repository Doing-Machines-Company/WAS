# db_to_google_test.py

import os
import asyncio
from datetime import datetime, timezone

from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler

# Import the syncing function from the utils file
from google_sync_utils import sync_user_to_google

# Track tasks so we can clean them up on shutdown
pending_tasks = set()
shutdown_event = asyncio.Event()

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
        task = asyncio.create_task(sync_user_to_google(supabase_handler, payload["payload"]["userId"]))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)
    else:
        print("❌ Invalid payload: Missing 'userId'")


async def shutdown(supabase_client, channel):
    """
    Properly shut down the application and cancel all pending tasks.
    """
    print("Shutting down...")

    for task in pending_tasks:
        task.cancel()

    if pending_tasks:
        await asyncio.wait(pending_tasks, timeout=5)

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
    """
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("ERROR: Missing required environment variables SUPABASE_URL and/or SUPABASE_KEY")
        print("Please set these environment variables and try again.")
        return 1

    print("\n=== Supabase to Google Calendar & Tasks Sync Listener ===\n")

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
    print("▶️ Press Ctrl+C to exit.")

    while not shutdown_event.is_set():
        await asyncio.sleep(1)

    await shutdown(supabase_client, channel)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received. Exiting...")

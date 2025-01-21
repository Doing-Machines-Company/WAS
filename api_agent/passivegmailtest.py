# passivegmailtest.py

import asyncio
import logging
from datetime import datetime

from gmail_new_mail_agent import GmailNewMailAgent
from api_functions import GmailAPIHandler

logging.basicConfig(level=logging.INFO)


def my_thread_criteria_func_v1(thread_data: dict) -> bool:
    """
    Example thread-level criteria function #1:
      - Return True if ANY in-timeframe message has 'bonk' in subject and snippet.
      - Because we only pass the in-timeframe messages, no need to filter further here.
    """
    messages = thread_data.get("messages", [])
    for msg in messages:
        snippet = (msg.get("snippet") or "").lower()
        if "bonk" not in snippet:
            continue

        headers = msg.get("payload", {}).get("headers", [])
        subject = ""
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "").lower()
                break

        if "bonk" in subject and "bonk" in snippet:
            return True
    return False


def my_thread_criteria_func_v2(thread_data: dict) -> bool:
    """
    Example thread-level criteria function #2:
      - Return True if ANY in-timeframe message has 'testing123' in snippet or subject.
    """
    messages = thread_data.get("messages", [])
    for msg in messages:
        snippet = (msg.get("snippet") or "").lower()
        if "testing123" in snippet:
            return True

        headers = msg.get("payload", {}).get("headers", [])
        subject = ""
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "").lower()
                break

        if "testing123" in subject:
            return True
    return False


def on_new_threads_callback(threads_list):
    """
    Called whenever we discover new threads that pass the criteria
    or whenever a tracked thread sees a new message (any change).
    """
    print(f"\n[CALLBACK] Received {len(threads_list)} thread(s):")
    for th in threads_list:
        tid = th.get("id")
        print(f"  - Thread ID = {tid}")
        # Possibly list message subjects
        for m in th.get("messages", []):
            subject = None
            for h in m.get("payload", {}).get("headers", []):
                if h.get("name", "").lower() == "subject":
                    subject = h.get("value", "")
                    break
            print(f"    * Message ID: {m.get('id')} Subject: {subject}")


async def main():
    gmail_handler = GmailAPIHandler()

    # Create the agent with an initial criteria function and no JSON storage
    agent = GmailNewMailAgent(
        check_interval_seconds=7,
        gmail_handler=gmail_handler,
        criteria_func=my_thread_criteria_func_v1,  # Start with criteria_func_v1
        timeframe_hours=24,                       # only consider last 24h for new matches
        label_ids=["INBOX"],                      # watch changes for threads that appear in INBOX
        last_history_id=None                      # if None, will set it at start
    )
    agent.on_tracked_change = on_new_threads_callback

    # Start the agent in the background
    task = asyncio.create_task(agent.start())

    # Let it run for ~30s
    print("Running with criteria_func_v1 for 30 seconds...")
    await asyncio.sleep(120)

    # Now suppose we want to change to a new criteria function on the fly
    print("\n*** NOW CHANGING THE CRITERIA FUNCTION to my_thread_criteria_func_v2 ***\n")
    await agent.new_criteria_reset(my_thread_criteria_func_v2)

    # Let it run for another ~30s to see new matches
    print("Running with criteria_func_v2 for another 30 seconds...")
    await asyncio.sleep(60)

    # Stop the agent
    agent.stop()
    await task

    # Show final stats
    all_cached = agent.get_all_cached_threads()
    print(f"\nTotal cached threads in memory: {len(all_cached)}")

    matched_now = agent.get_matching_threads()
    print(f"Threads that match the final criteria (v2): {len(matched_now)}")
    for th in matched_now:
        print(f" - Thread ID={th.get('id')}")


if __name__ == "__main__":
    asyncio.run(main())

# passivegmailtest.py

import asyncio
import logging
from datetime import datetime

from gmail_new_mail_agent import GmailNewMailAgent
from api_functions import GmailAPIHandler

logging.basicConfig(level=logging.INFO)


def my_thread_criteria_func(thread_data: dict) -> bool:
    """
    Example thread-level criteria function:
      - Return True if ANY message in the thread
        has 'bonk' in the subject and 'bonk' in the snippet.
      You can implement more advanced logic as needed.

    The entire thread object is structured like:
      {
        "id": "...",
        "messages": [
          {
            "id": "...",
            "threadId": "...",
            "labelIds": [...],
            "snippet": "...",
            "payload": {
              "headers": [...],
              "parts": [...],
              ...
            },
            "internalDate": "1673982840000"
          },
          ...
        ],
        ...
      }

    We'll check each message's subject/snippet for demonstration purposes.
    """
    messages = thread_data.get("messages", [])
    for msg in messages:
        snippet = (msg.get("snippet") or "").lower()
        # Must contain 'bonk' in snippet
        if "bonk" not in snippet:
            continue

        # Extract subject from headers
        headers = msg.get("payload", {}).get("headers", [])
        subject = ""
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "").lower()
                break

        if "bonk" in subject and "bonk" in snippet:
            return True

    return False


def on_new_matching_threads_callback(new_threads):
    """
    Called when new or updated threads match the criteria during polling
    OR when the agent starts up (after the initial crawl),
    if any threads already match the criteria.
    """
    print(f"\n[CALLBACK] Received {len(new_threads)} newly matched thread(s):")
    for th in new_threads:
        thread_id = th.get("id")
        print(f"  - Thread ID = {thread_id}")
        # Possibly list message subjects
        messages = th.get("messages", [])
        for m in messages:
            subject = None
            for h in m.get("payload", {}).get("headers", []):
                if h.get("name", "").lower() == "subject":
                    subject = h.get("value", "")
                    break
            print(f"    * Message ID: {m.get('id')} Subject: {subject}")


async def main():
    gmail_handler = GmailAPIHandler()

    agent = GmailNewMailAgent(
        check_interval_seconds=15,         # poll every 15 seconds
        gmail_handler=gmail_handler,
        criteria_func=my_thread_criteria_func,
        timeframe_hours=12,               # track threads with messages in the last 24 hours
        cache_json_path="my_gmail_cache.json",
        label_ids=["INBOX"],              # only watch 'INBOX' changes
        last_history_id=None              # if None, we'll set it at startup
    )

    # Set our callback for newly matching threads
    agent.on_new_matching_threads = on_new_matching_threads_callback

    # Start the agent in the background
    task = asyncio.create_task(agent.start())

    # Let it run for 1 minute for demonstration, then stop
    await asyncio.sleep(300)
    agent.stop()
    await task

    # Print how many threads are in the cache total
    all_cached = agent.get_all_cached_threads()
    print(f"\nTotal cached threads after run: {len(all_cached)}")

    # Show how many match the criteria right now
    matched = agent.get_matching_threads()
    print(f"Threads that match the criteria: {len(matched)}")
    for th in matched:
        print(f" - Thread ID={th.get('id')}")


if __name__ == "__main__":
    asyncio.run(main())

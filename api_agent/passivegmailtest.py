# passivegmailtest.py

import asyncio
import logging
from datetime import datetime

from agents.gmail.gmail_new_mail_agent import GmailNewMailAgent
from api_functions import GmailAPIHandler

logging.basicConfig(level=logging.INFO)


def my_thread_criteria_func_v1(thread_data: dict) -> bool:
    """
    Example #1:
    Return True if 'bonk' is found in both subject and snippet.
    """
    messages = thread_data.get("messages", [])
    for msg in messages:
        snippet = (msg.get("snippet") or "").lower()
        if "bonk1" not in snippet:
            continue

        headers = msg.get("payload", {}).get("headers", [])
        subject = ""
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "").lower()
                break

        if "bonk1" in subject and "bonk1" in snippet:
            return True
    return False

def my_thread_criteria_func_v2(thread_data: dict) -> bool:
    """
    Example #2:
    Return True if 'testing123' is found in subject or snippet.
    """
    messages = thread_data.get("messages", [])
    for msg in messages:
        snippet = (msg.get("snippet") or "").lower()
        if "bonk2" in snippet:
            return True

        headers = msg.get("payload", {}).get("headers", [])
        subject = ""
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "").lower()
                break

        if "bonk2" in subject:
            return True
    return False


def on_tracked_change(changes: dict):
    """
    `changes` is a dictionary of thread_id -> {"data": <thread_data>, "just_changed": bool}.
    """
    # 1) Log all threads received
    logging.info(f"[CALLBACK] Received {len(changes)} thread(s) this cycle:")
    for t_id, info in changes.items():
        thread_data = info["data"]
        logging.info(f"  - Thread ID={t_id}, snippetOfFirstMsg='{thread_data.get('messages', [{}])[0].get('snippet','')[:40]}'")

    # 2) Log which threads had just_changed=True
    changed = [t_id for t_id, info in changes.items() if info["just_changed"]]
    if changed:
        logging.info(f"[CALLBACK] Of these, {len(changed)} thread(s) were updated/changed:")
        for t_id in changed:
            thr_data = changes[t_id]["data"]
            logging.info(f"     * Thread ID={t_id}, totalMessages={len(thr_data.get('messages',[]))}")
    else:
        logging.info("[CALLBACK] None of these threads were newly updated/changed this time.")


async def main():
    gmail_handler = GmailAPIHandler()

    # Create the agent with an initial criteria function
    agent = GmailNewMailAgent(
        check_interval_seconds=7,
        gmail_handler=gmail_handler,
        criteria_func=my_thread_criteria_func_v1,  # Start with criteria_func_v1
        timeframe_hours=24,
        label_ids=["INBOX"],   # watch threads that appear in INBOX
        last_history_id=None
    )
    agent.on_tracked_change = on_tracked_change

    # Start the agent in the background
    task = asyncio.create_task(agent.start())

    # Let it run for ~30 seconds with the first criteria
    logging.info("Running with criteria_func_v1 for 30 seconds...")
    await asyncio.sleep(10)

    # Switch to new criteria
    logging.info("\n*** NOW CHANGING THE CRITERIA FUNCTION to my_thread_criteria_func_v2 ***\n")
    await agent.new_criteria_reset(my_thread_criteria_func_v2)

    # Let it run for another ~30 seconds
    logging.info("Running with criteria_func_v2 for 30 more seconds...")
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

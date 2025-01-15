# passivegmailtest.py

import asyncio
import logging

from gmail_new_mail_agent import GmailNewMailAgent
from api_functions import GmailAPIHandler

logging.basicConfig(level=logging.INFO)

def my_criteria_func(email_data: dict) -> bool:
    """
    Checks if subject has 'goodtest' AND snippet has 'goodtestbody'.
    """
    headers = email_data.get("payload", {}).get("headers", [])
    subject = ""
    for h in headers:
        if h.get("name", "").lower() == "subject":
            subject = h.get("value", "")
            break

    snippet = email_data.get("snippet", "") or ""
    return ("bonk" in subject.lower()) and ("bonk" in snippet.lower())

def on_new_mails_callback(new_items):
    print(f"\n[CALLBACK] Received {len(new_items)} new item(s):")
    for it in new_items:
        # item could be a message or a draft resource
        ident = it.get("id")
        snippet = it.get("snippet", "")
        print(f"  - ID={ident}, snippet[:50]={snippet[:50]}...")

async def main():
    gmail_handler = GmailAPIHandler()

    agent = GmailNewMailAgent(
        check_interval_seconds=10,
        gmail_handler=gmail_handler,
        criteria_func=my_criteria_func,
        label_ids=["INBOX"],
        last_history_id=None  # start from current
    )
    agent.on_new_mails = on_new_mails_callback

    task = asyncio.create_task(agent.start())

    # Let it run for 2 minutes
    await asyncio.sleep(120)
    agent.stop()
    await task

    # Print all matched items
    matched = agent.get_matching_mails()
    print(f"\nTotal matched items: {len(matched)}")
    for m in matched:
        print(f" - ID={m.get('id')}")

if __name__ == "__main__":
    asyncio.run(main())

# main.py

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
    return ("goodtest" in subject.lower()) and ("goodtestbody" in snippet.lower())

def on_new_mails(new_mails):
    """
    Callback that runs whenever the agent finds new matched messages.
    Print their IDs and snippet info.
    """
    print(f"\n[CALLBACK] Received {len(new_mails)} new matched mail(s):")
    for msg in new_mails:
        mail_id = msg.get("id")
        snippet = msg.get("snippet", "")
        print(f"  - ID={mail_id}, snippet[:50]={snippet[:50]}...")

async def main():
    # Create a Gmail API handler
    gmail_handler = GmailAPIHandler()

    # Optionally define a last_history_id if you want to start from a known point
    # For demonstration, let's leave it as None => ignore older mail on first run
    last_hid = None

    # Create the agent to check INBOX only, every 10s
    agent = GmailNewMailAgent(
        check_interval_seconds=10,
        gmail_handler=gmail_handler,
        criteria_func=my_criteria_func,
        label_ids=["INBOX", "SPAM"],
        last_history_id=last_hid
    )

    # Attach a callback so we see new mail immediately
    agent.on_new_mails = on_new_mails

    # Start the agent in an asyncio Task
    agent_task = asyncio.create_task(agent.start())

    # Let it run for 10 minutes
    await asyncio.sleep(600)

    # Stop the agent
    agent.stop()
    await agent_task

    # Print all matched messages so far (in case anything was missed in callback)
    all_matched = agent.get_matching_mails()
    print(f"\nFound {len(all_matched)} total matched message(s).")
    for m in all_matched:
        mail_id = m.get("id")
        subject = next(
            (h["value"] for h in m.get("payload", {}).get("headers", [])
             if h["name"].lower() == "subject"),
            "(no subject)"
        )
        print(f"  ID={mail_id}, subject={subject}")

if __name__ == "__main__":
    asyncio.run(main())

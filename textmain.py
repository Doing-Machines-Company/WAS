# textmain.py

import os
import uvicorn
from fastapi import FastAPI, Request, Form
from SMSAgent import SMSAgent

app = FastAPI()

# NEED TO USE ngrok for local testing, will set up static when twilio gives us perms

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "ACef0545f40781e8fdb200f253bd63accc")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "[AUTH TOKE]")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER", "+18887758140")

@app.post("/sms")
async def receive_sms(
    request: Request
):
    """
    This endpoint will be called by Twilio whenever an SMS is sent
    to your Twilio number. Twilio will POST form-encoded parameters
    including 'From' and 'Body'.
    """
    form_data = await request.form()
    from_number = form_data.get("From")
    body = form_data.get("Body")

    # Instantiate the agent (could also be done at a global level)
    sms_agent = SMSAgent(ACCOUNT_SID, AUTH_TOKEN, TWILIO_NUMBER)

    # Handle the incoming message asynchronously
    await sms_agent.handle_incoming_message(from_number, body)

    # Twilio typically expects a TwiML response,
    # but if you're directly sending a separate message via the API,
    # returning a simple text or empty string often suffices.
    return "OK"


def start():
    """
    Launch the FastAPI application using Uvicorn.
    """
    uvicorn.run(
        "textmain:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # reload=True is useful for local development
    )

if __name__ == "__main__":
    start()

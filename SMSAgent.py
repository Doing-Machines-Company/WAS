import asyncio
from twilio.rest import Client


class SMSAgent:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        """
        Initialize the SMSAgent with Twilio credentials and a Twilio phone number.
        :param account_sid: Your Twilio Account SID
        :param auth_token: Your Twilio Auth Token
        :param from_number: The Twilio phone number you are using (e.g. '+18777804236')
        """
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    async def handle_incoming_message(self, from_number: str, message_body: str) -> str:
        """
        Upon receiving a text, do some internal operations (placeholder),
        then send back a response using Twilio.

        :param from_number: The phone number that sent the message
        :param message_body: The content of the inbound message
        :return: The SID of the message sent back (for logging or debugging)
        """
        # Placeholder for any internal operations you might need
        # (database queries, AI calls, computations, etc.)
        processed_response = self._do_internal_operations(message_body)

        # Send a text response to the incoming number
        # Twilio's messages.create is a blocking call, so we run it in an async executor
        loop = asyncio.get_running_loop()
        message = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                body=processed_response,
                from_=self.from_number,
                to=from_number
            )
        )
        return message.sid

    def _do_internal_operations(self, inbound_text: str) -> str:
        """
        Placeholder for internal logic.
        Return any string that you want to send back as the response.
        """
        # For demonstration, just return a fixed or formatted string
        return f"Thanks for your message! You said: {inbound_text}"

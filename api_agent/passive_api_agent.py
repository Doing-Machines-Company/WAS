# passive_api_agent.py

import asyncio
import logging

logger = logging.getLogger(__name__)

class PassiveAPIAgent:
    """
    Base class for a 'passive' agent that periodically does some polling
    in a single handle_polling method.
    """

    def __init__(self, check_interval_seconds: int = 60):
        self.check_interval_seconds = check_interval_seconds
        self._stop_requested = False

    async def start(self):
        """
        Main loop that waits for check_interval_seconds,
        then calls handle_polling() until stop() is requested.
        """
        logger.info("PassiveAPIAgent started.")
        while not self._stop_requested:
            await asyncio.sleep(self.check_interval_seconds)
            try:
                await self.handle_polling()
            except Exception as e:
                logger.error(f"Error in handle_polling: {e}")

        logger.info("PassiveAPIAgent stopped.")

    def stop(self):
        self._stop_requested = True

    async def handle_polling(self):
        """
        Subclasses implement all check+action logic in this single method.
        """
        raise NotImplementedError("Subclasses must implement handle_polling()")

    async def new_criteria_reset(self):
        """
        Subtask should handle logic.
        """
        raise NotImplementedError("Subclasses must implement new_criteria_reset()")

    async def on_tracked_change(self):
        """
        Subtask should handle logic.
        """
        raise NotImplementedError("Subclasses must implement on_tracked_change()")

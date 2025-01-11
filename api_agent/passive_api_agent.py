# passive_api_agent.py

import asyncio
import logging

logger = logging.getLogger(__name__)

class PassiveAPIAgent:
    """
    A generic base class for a 'passive' API agent that periodically checks
    some condition and performs actions if that condition is met.
    """

    def __init__(self, check_interval_seconds: int = 60):
        """
        :param check_interval_seconds: How often (in seconds) to run check_condition().
        """
        self.check_interval_seconds = check_interval_seconds
        self._stop_requested = False

    async def start(self):
        """
        Main loop that:
          1) Waits for check_interval_seconds
          2) Calls check_condition()
          3) If condition is True, calls perform_actions()
          4) Repeats until stop() is called
        """
        logger.info("PassiveAPIAgent started.")
        while not self._stop_requested:
            await asyncio.sleep(self.check_interval_seconds)

            condition_met = await self.check_condition()
            if condition_met:
                try:
                    await self.perform_actions()
                except Exception as e:
                    logger.error(f"Error in perform_actions: {e}")

        logger.info("PassiveAPIAgent stopped.")

    def stop(self):
        """
        Signals the agent to stop after the current iteration.
        """
        self._stop_requested = True

    async def check_condition(self) -> bool:
        """
        Subclasses must implement how they detect if the condition is met.
        Return True if condition is met, otherwise False.
        """
        raise NotImplementedError("Subclasses must implement check_condition()")

    async def perform_actions(self):
        """
        Subclasses must implement the actions to perform when condition_met is True.
        """
        raise NotImplementedError("Subclasses must implement perform_actions()")

# google_tasks_event_change.py

import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime

from passive_api_agent import PassiveAPIAgent
from api_functions import GoogleTasksAPIHandler

logger = logging.getLogger(__name__)

class GTasksChangeAgent(PassiveAPIAgent):
    """
    A passive agent that polls Google Tasks for changes using updated timestamps.

    Behavior:
      - On first run (per tasklist):
        * We do NOT show old deleted tasks.
        * We build the internal cache of existing tasks.
        * We immediately notify the callback of pre-existing (non-deleted) tasks that match criteria.
      - On subsequent runs:
        * We fetch tasks updated since last_updated_time, including newly deleted tasks.
        * We determine create/update/delete changes by comparing to the cache.
        * We notify the callback of any changes that match criteria.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        tasks_handler: Optional[GoogleTasksAPIHandler],
        criteria_func: Callable[[dict], bool],
        tasklist_ids: Optional[List[str]] = None
    ):
        super().__init__(check_interval_seconds)
        self.tasks_handler = tasks_handler or GoogleTasksAPIHandler()
        self.criteria_func = criteria_func

        # If user did not provide lists => dynamic mode
        self._dynamic_tasklists = not bool(tasklist_ids)
        self.tasklist_ids = tasklist_ids or []

        # Where we store tasks that matched criteria across time
        self._matching_tasks: List[dict] = []
        # Where we store info about ALL changes observed
        # (including created, updated, deleted, and possibly no-change).
        self._all_changes: List[dict] = []
        # task_id -> last known version of the task
        self._task_cache: Dict[str, dict] = {}
        # tasklist_id -> last known updated timestamp
        self._last_updated_time: Dict[str, str] = {}

        # Optional callback: called when we detect newly relevant tasks
        self.on_new_tasks: Optional[Callable[[List[dict]], None]] = None

    async def handle_polling(self):
        """
        Main polling loop. If _dynamic_tasklists is True, we fetch all lists each time.
        Otherwise, we use the provided self.tasklist_ids.
        """
        if self._dynamic_tasklists:
            logger.info("GTasksChangeAgent => In dynamic mode, fetching all user's tasklists...")
            all_lists = self.tasks_handler.list_tasklists()
            current_ids = [lst["id"] for lst in all_lists if "id" in lst]
            logger.info(f"GTasksChangeAgent => Found {len(current_ids)} tasklists to monitor.")
        else:
            current_ids = self.tasklist_ids
            logger.info(f"GTasksChangeAgent => Using user-supplied tasklist_ids: {current_ids}")

        for tlist_id in current_ids:
            logger.info(f"GTasksChangeAgent => Checking task list '{tlist_id}'...")
            if tlist_id not in self._last_updated_time:
                logger.info(f"GTasksChangeAgent => First run for list '{tlist_id}'")
                # On first run, we skip old deletions => show_deleted=False
                await self._handle_first_run(tlist_id, show_deleted=False)
            else:
                updated_min = self._last_updated_time[tlist_id]
                logger.info(f"GTasksChangeAgent => Using updatedMin={updated_min} for list '{tlist_id}'")
                # On subsequent runs, we do show_deleted=True to detect new deletions
                new_items = await self._handle_incremental_run(tlist_id, show_deleted=True)
                if new_items and self.on_new_tasks:
                    self.on_new_tasks(new_items)
                self._matching_tasks.extend(new_items)

        logger.info("Polling Cycle Complete for all lists.")

    async def _handle_first_run(self, tlist_id: str, show_deleted: bool):
        """
        Baseline fetch of tasks in this list.
        We do NOT consider them as 'changes', but we DO call on_new_tasks for
        any non-deleted tasks that match the criteria.
        """
        try:
            resp = (
                self.tasks_handler.service.tasks()
                .list(tasklist=tlist_id, showHidden=True, showDeleted=show_deleted)
                .execute()
            )
            tasks = resp.get("items", [])
        except Exception as e:
            logger.error(f"GTasksChangeAgent => Error during first-run fetch: {e}")
            return

        max_updated = None
        first_run_new_items = []
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue

            self._task_cache[tid] = t
            is_deleted = t.get("deleted", False)

            # If it's not deleted, check if it meets the criteria
            if not is_deleted and self.criteria_func(t):
                first_run_new_items.append(t)

            # Track largest updated time
            this_updated = t.get("updated")
            if this_updated and (max_updated is None or this_updated > max_updated):
                max_updated = this_updated

        # If we found pre-existing tasks that meet criteria, send them to callback now
        if first_run_new_items and self.on_new_tasks:
            self.on_new_tasks(first_run_new_items)
        self._matching_tasks.extend(first_run_new_items)

        # Store last_updated_time
        if max_updated:
            self._last_updated_time[tlist_id] = max_updated
        else:
            # No tasks or no updated => fallback to "now"
            self._last_updated_time[tlist_id] = datetime.utcnow().isoformat() + "Z"

        logger.info(
            f"GTasksChangeAgent => First run complete. Fetched {len(tasks)} tasks "
            f"from '{tlist_id}'. {len(first_run_new_items)} matched criteria and were reported."
        )

    async def _handle_incremental_run(self, tlist_id: str, show_deleted: bool) -> List[dict]:
        """
        Fetch tasks updated since last run, detect changes, and return any new/updated/deleted tasks
        that meet criteria.
        """
        new_items = []
        updated_min = self._last_updated_time[tlist_id]

        try:
            resp = (
                self.tasks_handler.service.tasks()
                .list(tasklist=tlist_id, showHidden=True, showDeleted=show_deleted, updatedMin=updated_min)
                .execute()
            )
            tasks = resp.get("items", [])
        except Exception as e:
            logger.error(f"GTasksChangeAgent => Error during incremental fetch: {e}")
            return new_items

        logger.info(f"GTasksChangeAgent => Found {len(tasks)} changed task(s) in '{tlist_id}'.")
        changes_this_round = []
        max_updated_str = updated_min

        for t in tasks:
            change_info = self._describe_change(t)
            changes_this_round.append(change_info)

            logger.info(
                f"GTasksChangeAgent => Change for task_id={change_info['id']}, "
                f"change_type={change_info['change_type']}, diffs={change_info['diffs']}"
            )

            # Decide if we should pass this to new_items
            if change_info["change_type"] == "created":
                if self.criteria_func(change_info["new_data"]):
                    new_items.append(change_info["new_data"])

            elif change_info["change_type"] == "updated":
                if self.criteria_func(change_info["new_data"]):
                    new_items.append(change_info["new_data"])

            elif change_info["change_type"] == "deleted":
                # For a newly deleted task, we check if the OLD data matched the criteria
                old_data = change_info["old_data"]
                if old_data and self.criteria_func(old_data):
                    # We pass the new_data (which has "deleted": True) so user sees it's gone
                    new_items.append(change_info["new_data"])

            this_updated = t.get("updated")
            if this_updated and this_updated > max_updated_str:
                max_updated_str = this_updated

        self._all_changes.extend(changes_this_round)
        self._last_updated_time[tlist_id] = max_updated_str

        logger.info(f"GTasksChangeAgent => Found {len(new_items)} matching task(s) for '{tlist_id}'.")
        return new_items

    def _describe_change(self, new_data: dict) -> dict:
        """
        Compare new_data with our cache to classify the change as created, updated, or deleted.
        Also record the diffs, plus old_data/new_data.
        """
        tid = new_data.get("id", "")
        old_data = self._task_cache.get(tid, {})
        is_deleted = new_data.get("deleted", False)

        if is_deleted:
            change_type = "deleted"
            diffs = self._compute_diff(old_data, new_data)
        else:
            if not old_data:
                change_type = "created"
                diffs = self._compute_diff({}, new_data)
            else:
                diffs = self._compute_diff(old_data, new_data)
                change_type = "updated" if diffs else "no-change"

        # Update the cache
        self._task_cache[tid] = new_data

        return {
            "id": tid,
            "change_type": change_type,
            "old_data": old_data,
            "new_data": new_data,
            "diffs": diffs
        }

    def _compute_diff(self, old_data: dict, new_data: dict) -> dict:
        """
        Shallow compare of old_data and new_data fields, returning a dict
        of { field: { "old": X, "new": Y } } for changed fields.
        """
        changes = {}
        all_keys = set(old_data.keys()).union(new_data.keys())
        for k in all_keys:
            old_val = old_data.get(k)
            new_val = new_data.get(k)
            if old_val != new_val:
                changes[k] = {"old": old_val, "new": new_val}
        return changes

    def get_matching_tasks(self) -> List[dict]:
        """
        Return all tasks that have ever met criteria during first-run or incremental runs.
        """
        return self._matching_tasks

    def get_all_changes(self) -> List[dict]:
        """
        Return a list describing all observed changes (including 'no-change' if it had diffs=0).
        Each entry is a dict with keys: id, change_type, old_data, new_data, diffs
        """
        return self._all_changes

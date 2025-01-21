# google_tasks_change.py

import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any, Set
from datetime import datetime
from dateutil import parser

from passive_api_agent import PassiveAPIAgent
from api_functions import GoogleTasksAPIHandler

logger = logging.getLogger(__name__)


class GTasksChangeAgent(PassiveAPIAgent):
    """
    A passive agent that polls Google Tasks for changes using updated timestamps.

    Unique behaviors:
      - Once a task is added to the active tracking set, it remains forever,
        unless it is deleted.
      - Any update or deletion to a task in the active tracking set triggers
        a callback (on_new_tasks).
      - A task not in the set is only added if it meets the criteria upon
        creation or update. If it later stops meeting the criteria, it stays
        in the set.
      - On first run, we skip old deletions (showDeleted=False).
      - On incremental runs, showDeleted=True to detect new deletions.
      - new_criteria_reset() can add tasks that now meet the new criteria,
        but does not remove tasks that previously met old criteria.
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

        # The user-supplied function that decides if a task is "interesting."
        self.criteria_func = criteria_func

        # If user did not provide lists => dynamic mode
        self._dynamic_tasklists = not bool(tasklist_ids)
        self.tasklist_ids = tasklist_ids or []

        # For each tasklist: the last known updated timestamp (RFC3339 string)
        self._last_updated_time: Dict[str, str] = {}

        # 1) The main cache: task_id -> task_data (for tasks that are not deleted)
        self._task_cache: Dict[str, dict] = {}

        # 2) The active tracking set: a set of task_ids that have
        #    ever met the criteria (unless deleted)
        self._active_tracking_set: Set[str] = set()

        # For debugging/logging: a list of all observed changes
        self._all_changes: List[dict] = []

        # Callback to be fired on newly relevant tasks OR changes/deletions
        # of tasks already in the set
        self.on_tracked_change: Optional[Callable[[List[dict]], None]] = None

    # -------------------------
    # Public utility methods
    # -------------------------
    def get_cache_size(self) -> int:
        """Return how many items are currently in the task cache."""
        return len(self._task_cache)

    def get_active_keys(self) -> Set[str]:
        """Return a copy of the set of active (matching) task IDs."""
        return set(self._active_tracking_set)

    def get_all_changes(self) -> List[dict]:
        """
        Return the log of all changes observed so far.
        Each item is { 'id', 'change_type', 'old_data', 'new_data', 'diffs' }.
        """
        return self._all_changes

    def get_active_tasks(self) -> List[dict]:
        """
        Return a list of the actual task dicts for those IDs in _active_tracking_set
        that are still in the cache (i.e. not deleted).
        """
        return [self._task_cache[tid] for tid in self._active_tracking_set if tid in self._task_cache]

    async def new_criteria_reset(self, new_criteria_func: Optional[Callable[[dict], bool]] = None):
        """
        1) Optionally update the criteria function.
        2) Immediately poll once (so we have the latest data in _task_cache).
        3) COMPLETELY REPLACE the _active_tracking_set by checking the new (or same) criteria
           for ALL tasks in _task_cache.
           => This overrides the "once in, always in" for normal operation.
        """

        # 1) Update the criteria if provided
        if new_criteria_func is not None:
            self.criteria_func = new_criteria_func

        # 2) Do an immediate poll to ensure _task_cache is up-to-date
        await self.handle_polling()

        # 3) Build a brand-new active set based on the current criteria
        old_active = self._active_tracking_set
        new_active = set()

        for tid, data in self._task_cache.items():
            # Make sure it's not marked deleted
            if not data.get("deleted", False):
                # If it passes the (new) criteria, add it
                if self.criteria_func(data):
                    new_active.add(tid)

        # Overwrite the old set
        self._active_tracking_set = new_active

        logger.info(
            f"[new_criteria_reset] Rebuilt _active_tracking_set from scratch. "
            f"Old size = {len(old_active)}, new size = {len(self._active_tracking_set)}. "
        )

    # -------------------------
    # Internal Polling Methods
    # -------------------------
    async def handle_polling(self):
        """
        Main polling loop. If _dynamic_tasklists is True, fetch all lists each time.
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
            if tlist_id not in self._last_updated_time:
                # First run => skip old deletions
                logger.info(f"[First Run] TaskList={tlist_id}")
                await self._handle_first_run(tlist_id)
            else:
                updated_min = self._last_updated_time[tlist_id]
                logger.info(f"[Incremental] TaskList={tlist_id}, updatedMin={updated_min}")
                new_items = await self._handle_incremental_run(tlist_id)
                # If we found newly relevant items or changes to existing
                # tracked items, we call the callback
                if new_items and self.on_tracked_change:
                    self.on_tracked_change(new_items)

        logger.info("Polling Cycle Complete for all lists.")

    async def _handle_first_run(self, tlist_id: str):
        """
        On first run, we do showDeleted=False so tasks deleted before agent start
        won't appear. We store tasks in _task_cache, and any that pass the criteria
        get added to _active_tracking_set. We call the callback with those items
        since they're "preexisting but relevant."
        """
        try:
            resp = (
                self.tasks_handler.service.tasks()
                .list(tasklist=tlist_id, showHidden=True, showDeleted=False)
                .execute()
            )
            tasks = resp.get("items", [])
        except Exception as e:
            logger.error(f"[First Run] Error fetching tasks for {tlist_id}: {e}")
            return

        max_updated = None
        newly_relevant = []
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue

            # Add to the cache
            self._task_cache[tid] = t

            # If it meets criteria, add to the set
            if self.criteria_func(t):
                self._active_tracking_set.add(tid)
                newly_relevant.append(t)

            # Track largest updated time
            t_updated = t.get("updated")
            if t_updated and (max_updated is None or t_updated > max_updated):
                max_updated = t_updated

        # If we found tasks that meet the criteria, callback
        if newly_relevant and self.on_tracked_change:
            self.on_tracked_change(newly_relevant)

        if max_updated:
            self._last_updated_time[tlist_id] = max_updated
        else:
            self._last_updated_time[tlist_id] = datetime.utcnow().isoformat() + "Z"

        logger.info(
            f"[First Run] {tlist_id}: fetched {len(tasks)} tasks, "
            f"{len(newly_relevant)} matched criteria."
        )

    async def _handle_incremental_run(self, tlist_id: str) -> List[dict]:
        """
        On subsequent runs, we do showDeleted=True so newly deleted items are detected.
        We'll fetch tasks updated after last_updated_time, filter out anything
        with an updated timestamp <= that min, then see if it's created, updated, or deleted.

        Return a list of tasks that should trigger a callback:
         - newly relevant tasks (i.e. not in the set, but pass criteria now)
         - any changes to tasks that are already in the set (including deletion)
        """
        updated_min_str = self._last_updated_time[tlist_id]
        new_items: List[dict] = []

        try:
            resp = (
                self.tasks_handler.service.tasks()
                .list(
                    tasklist=tlist_id,
                    showHidden=True,
                    showDeleted=True,
                    updatedMin=updated_min_str
                )
                .execute()
            )
            tasks = resp.get("items", [])
        except Exception as e:
            logger.error(f"[Incremental] Error fetching tasks for {tlist_id}: {e}")
            return new_items

        logger.info(f"[Incremental] {tlist_id}: server returned {len(tasks)} tasks.")
        baseline_dt = parser.isoparse(updated_min_str)
        filtered_tasks = []
        for t in tasks:
            t_upd_str = t.get("updated")
            if not t_upd_str:
                continue
            try:
                t_dt = parser.isoparse(t_upd_str)
            except:
                continue
            if t_dt > baseline_dt:
                filtered_tasks.append(t)

        logger.info(f"[Incremental] {tlist_id}: {len(filtered_tasks)} tasks have updated > {updated_min_str}.")
        max_updated_str = updated_min_str
        changes_this_round = []

        for t in filtered_tasks:
            change = self._describe_change(t)
            changes_this_round.append(change)
            ctype = change["change_type"]
            old_data = change["old_data"]
            new_data = change["new_data"]

            logger.info(
                f"[Incremental] {tlist_id} => Task {change['id']}, {ctype}, diffs={change['diffs']}"
            )

            task_id = change["id"]

            if ctype == "created":
                # If it meets criteria, add to set => callback
                if not new_data.get("deleted", False) and self.criteria_func(new_data):
                    self._active_tracking_set.add(task_id)
                    new_items.append(new_data)
                # If it doesn't pass criteria, do nothing.

            elif ctype == "updated":
                # If it's already in the set => ALWAYS callback
                # (the user wants any changes to tracked items => callback)
                if task_id in self._active_tracking_set:
                    new_items.append(new_data)
                else:
                    # If it's not in the set but now meets criteria => add + callback
                    if not new_data.get("deleted", False) and self.criteria_func(new_data):
                        self._active_tracking_set.add(task_id)
                        new_items.append(new_data)
                # We do NOT remove it if it fails criteria; "once in, stays in."

            elif ctype == "deleted":
                # If the old_data was in the set => callback
                if task_id in self._active_tracking_set:
                    # Show the new_data with deleted=True
                    new_items.append(new_data)
                    # And remove from both cache + set
                    self._prune_item(task_id)
                else:
                    # If we never tracked it, it's just no-change from our perspective
                    pass

            # "no-change" can happen if the API re-sends the same data
            # we won't do anything for no-change

            # Update max_updated
            upd_str = new_data.get("updated")
            if upd_str and upd_str > max_updated_str:
                max_updated_str = upd_str

        self._all_changes.extend(changes_this_round)
        self._last_updated_time[tlist_id] = max_updated_str
        logger.info(f"[Incremental] {tlist_id}: Found {len(new_items)} tasks that trigger a callback. Currently tracking {len(self._active_tracking_set)} items. ")
        return new_items

    def _describe_change(self, new_data: dict) -> dict:
        """
        Compare new_data to our cache to classify as created, updated, or deleted.
        Then update the cache if not deleted. Return a dict describing the change:
          { 'id': ..., 'change_type': 'created'/'updated'/'deleted'/'no-change',
            'old_data': ..., 'new_data': ..., 'diffs': ... }
        """
        tid = new_data.get("id", "")
        old_data = self._task_cache.get(tid, {})
        is_deleted = new_data.get("deleted", False)

        if is_deleted:
            # If we never had it => it was deleted before we started => 'no-change'
            if not old_data:
                return {
                    "id": tid,
                    "change_type": "no-change",
                    "old_data": {},
                    "new_data": new_data,
                    "diffs": {}
                }
            else:
                # It's newly deleted => find diffs
                diffs = self._compute_diff(old_data, new_data)
                change_type = "deleted"
                # We do NOT update the cache here, we'll prune it in _handle_incremental_run
        else:
            if not old_data:
                # brand new => 'created'
                diffs = self._compute_diff({}, new_data)
                change_type = "created"
                self._task_cache[tid] = new_data
            else:
                diffs = self._compute_diff(old_data, new_data)
                if diffs:
                    change_type = "updated"
                    self._task_cache[tid] = new_data
                else:
                    change_type = "no-change"

        return {
            "id": tid,
            "change_type": change_type,
            "old_data": old_data,
            "new_data": new_data,
            "diffs": diffs
        }

    def _compute_diff(self, old_data: dict, new_data: dict) -> dict:
        """Return a shallow dict of changed fields."""
        changes = {}
        all_keys = set(old_data.keys()) | set(new_data.keys())
        for k in all_keys:
            old_val = old_data.get(k)
            new_val = new_data.get(k)
            if old_val != new_val:
                changes[k] = {"old": old_val, "new": new_val}
        return changes

    def _prune_item(self, task_id: str):
        """
        Removes this task from the cache AND from the active tracking set.
        Called when we confirm a tracked item is newly deleted.
        """
        self._task_cache.pop(task_id, None)
        self._active_tracking_set.discard(task_id)

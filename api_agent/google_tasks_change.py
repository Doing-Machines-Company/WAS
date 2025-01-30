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
        a callback (on_tracked_change).
      - A task not in the set is only added if it meets the criteria upon
        creation or update. If it later stops meeting the criteria, it stays
        in the set.
      - On first run, we skip old deletions (showDeleted=False).
      - On incremental runs, showDeleted=True to detect new deletions.
      - new_criteria_reset() can add tasks that now meet the new criteria,
        but does not remove tasks that previously met old criteria.

    IT IS VERY IMPORTANT TO NOTE THAT CHILDREN DO NOT GET ADDED TO ACTIVE SET, JUST BECAUSE THEY ARE CHILD OF PARENT THAT IS
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

        # 1) The main cache: task_id -> task_data (for tasks not deleted)
        self._task_cache: Dict[str, dict] = {}

        # 2) The active tracking set: a set of task_ids that have
        #    ever met the criteria (unless deleted)
        self._active_tracking_set: Set[str] = set()

        # For debugging/logging: a list of all observed changes
        self._all_changes: List[dict] = []

        # Now on_tracked_change always takes a dictionary keyed by task_id
        # each containing {"data": ..., "just_changed": bool}
        self.on_tracked_change: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

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
        Return the dicts for those IDs in _active_tracking_set
        that are still in the cache (not deleted).
        """
        return [self._task_cache[tid] for tid in self._active_tracking_set if tid in self._task_cache]

    async def new_criteria_reset(self, new_criteria_func: Optional[Callable[[dict], bool]] = None):
        """
        1) Optionally update the criteria function.
        2) Immediately poll once (so we have the latest data in _task_cache).
        3) COMPLETELY REPLACE the _active_tracking_set by checking
           the new (or same) criteria for ALL tasks in _task_cache.
        """
        if new_criteria_func is not None:
            self.criteria_func = new_criteria_func

        # Do an immediate poll
        await self.handle_polling()

        # Rebuild the active set from scratch
        old_active = self._active_tracking_set
        new_active = set()
        for tid, data in self._task_cache.items():
            if not data.get("deleted", False):
                if self.criteria_func(data):
                    new_active.add(tid)

        self._active_tracking_set = new_active
        logger.info(
            f"[new_criteria_reset] Rebuilt _active_tracking_set from scratch. "
            f"Old size = {len(old_active)}, new size = {len(self._active_tracking_set)}. "
        )

    async def handle_polling(self):
        """
        Main polling entry point. If _dynamic_tasklists is True, fetch all lists each time.
        Otherwise, use the provided self.tasklist_ids.
        Then do either a first_run or incremental run per list.
        Finally, do one unified callback with the entire active set,
        marking which items changed in this poll.
        """
        changed_ids: Set[str] = set()

        if self._dynamic_tasklists:
            logger.info("GTasksChangeAgent => In dynamic mode, fetching all user's tasklists...")
            all_lists = self.tasks_handler.list_tasklists()
            current_ids = [lst["id"] for lst in all_lists if "id" in lst]
            logger.info(f"GTasksChangeAgent => Found {len(current_ids)} tasklists to monitor.")
        else:
            current_ids = self.tasklist_ids
            logger.info(f"GTasksChangeAgent => Using user-supplied tasklist_ids: {current_ids}")

        # Poll each tasklist
        for tlist_id in current_ids:
            if tlist_id not in self._last_updated_time:
                # first-run
                logger.info(f"[First Run] TaskList={tlist_id}")
                newly_changed = await self._handle_first_run(tlist_id)
                changed_ids.update(newly_changed)
            else:
                # incremental
                updated_min = self._last_updated_time[tlist_id]
                logger.info(f"[Incremental] TaskList={tlist_id}, updatedMin={updated_min}")
                newly_changed = await self._handle_incremental_run(tlist_id)
                changed_ids.update(newly_changed)

        # End-of-poll callback with the entire active set
        if self.on_tracked_change:
            # 1) Find all tasks whose parent is in the active set.
            child_ids = {
                tid for tid, data in self._task_cache.items()
                if data.get("parent") in self._active_tracking_set
            }
            # 2) We'll report these child tasks in the callback,
            #    but NOT add them to _active_tracking_set.
            callback_ids = self._active_tracking_set.union(child_ids)

            # 3) Build the callback payload for both active tasks + their children
            payload = {}
            for tid in callback_ids:
                payload[tid] = {
                    "data": self._task_cache[tid],
                    "just_changed": (tid in changed_ids)
                }

            # 4) Fire the callback
            self.on_tracked_change(payload)

        logger.info("Polling Cycle Complete for all lists.")


    async def _handle_first_run(self, tlist_id: str) -> Set[str]:
        """
        showDeleted=False so tasks deleted before agent start won't appear.
        We store tasks in _task_cache; any that pass criteria go in _active_tracking_set.
        Return set of IDs that "changed" (i.e., newly discovered & relevant).
        """
        changed_ids = set()
        try:
            resp = (
                self.tasks_handler.service.tasks()
                .list(tasklist=tlist_id, showHidden=True, showDeleted=False)
                .execute()
            )
            tasks = resp.get("items", [])
        except Exception as e:
            logger.error(f"[First Run] Error fetching tasks for {tlist_id}: {e}")
            return changed_ids

        max_updated = None
        newly_relevant = []
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue

            # Add to cache
            self._task_cache[tid] = t

            # Check criteria
            if self.criteria_func(t):
                self._active_tracking_set.add(tid)
                newly_relevant.append(t)
                changed_ids.add(tid)  # it's a newly discovered item meeting criteria

            # Track largest updated time
            t_updated = t.get("updated")
            if t_updated and (max_updated is None or t_updated > max_updated):
                max_updated = t_updated

        # If there's no updated time from any task, seed with "now"
        if max_updated:
            self._last_updated_time[tlist_id] = max_updated
        else:
            self._last_updated_time[tlist_id] = datetime.utcnow().isoformat() + "Z"

        logger.info(
            f"[First Run] {tlist_id}: fetched {len(tasks)} tasks, "
            f"{len(newly_relevant)} matched criteria."
        )
        return changed_ids

    async def _handle_incremental_run(self, tlist_id: str) -> Set[str]:
        """
        showDeleted=True so newly deleted items are detected.
        Return set of IDs that changed (i.e. newly relevant or updated or deleted).
        """
        changed_ids = set()
        updated_min_str = self._last_updated_time[tlist_id]

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
            return changed_ids

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
            if t_dt >= baseline_dt:
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
            task_id = change["id"]

            logger.info(
                f"[Incremental] {tlist_id} => Task {task_id}, {ctype}, diffs={change['diffs']}"
            )

            # If 'created' or 'updated' or 'deleted', we may add them to changed_ids if they are
            # relevant to the active set in any way
            if ctype == "created":
                if not new_data.get("deleted", False) and self.criteria_func(new_data):
                    self._active_tracking_set.add(task_id)
                    changed_ids.add(task_id)

            elif ctype == "updated":
                if task_id in self._active_tracking_set:
                    changed_ids.add(task_id)
                else:
                    if not new_data.get("deleted", False) and self.criteria_func(new_data):
                        self._active_tracking_set.add(task_id)
                        changed_ids.add(task_id)

            elif ctype == "deleted":
                if task_id in self._active_tracking_set:
                    changed_ids.add(task_id)
                    self._prune_item(task_id)

            # Update max_updated
            upd_str = new_data.get("updated")
            if upd_str and upd_str > max_updated_str:
                max_updated_str = upd_str

        self._all_changes.extend(changes_this_round)
        self._last_updated_time[tlist_id] = max_updated_str
        logger.info(
            f"[Incremental] {tlist_id}: Found {len(changed_ids)} tasks that changed in this round. "
            f"Currently tracking {len(self._active_tracking_set)} items."
        )
        return changed_ids

    def _describe_change(self, new_data: dict) -> dict:
        """
        Compare new_data to our cache => classify as created, updated, deleted, or no-change.
        Then update the cache if not deleted.
        """
        tid = new_data.get("id", "")
        old_data = self._task_cache.get(tid, {})
        is_deleted = new_data.get("deleted", False)

        if is_deleted:
            # If we never had it => it was deleted before we started => no-change
            if not old_data:
                return {
                    "id": tid,
                    "change_type": "no-change",
                    "old_data": {},
                    "new_data": new_data,
                    "diffs": {}
                }
            else:
                # newly deleted => find diffs
                diffs = self._compute_diff(old_data, new_data)
                return {
                    "id": tid,
                    "change_type": "deleted",
                    "old_data": old_data,
                    "new_data": new_data,
                    "diffs": diffs
                }
        else:
            if not old_data:
                # brand new => 'created'
                diffs = self._compute_diff({}, new_data)
                self._task_cache[tid] = new_data
                return {
                    "id": tid,
                    "change_type": "created",
                    "old_data": {},
                    "new_data": new_data,
                    "diffs": diffs
                }
            else:
                diffs = self._compute_diff(old_data, new_data)
                if diffs:
                    self._task_cache[tid] = new_data
                    return {
                        "id": tid,
                        "change_type": "updated",
                        "old_data": old_data,
                        "new_data": new_data,
                        "diffs": diffs
                    }
                else:
                    # no actual change
                    return {
                        "id": tid,
                        "change_type": "no-change",
                        "old_data": old_data,
                        "new_data": new_data,
                        "diffs": {}
                    }

    def _compute_diff(self, old_data: dict, new_data: dict) -> dict:
        """Return a shallow dict of changed fields."""
        changes = {}
        all_keys = set(old_data.keys()) | set(new_data.keys())
        for k in all_keys:
            if old_data.get(k) != new_data.get(k):
                changes[k] = {"old": old_data.get(k), "new": new_data.get(k)}
        return changes

    def _prune_item(self, task_id: str):
        """
        Removes this task from the cache AND from the active tracking set.
        Called when we confirm a tracked item is newly deleted.
        """
        self._task_cache.pop(task_id, None)
        self._active_tracking_set.discard(task_id)


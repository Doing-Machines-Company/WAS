# arxiv_passive_agent.py

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Any, Set, Optional

import arxiv

from passive_api_agent import PassiveAPIAgent

logger = logging.getLogger(__name__)

def extract_arxiv_base_and_version(short_id: str):
    """
    Given something like '2501.18595v1', returns:
      base_id='2501.18595', version_str='v1', version_num=1
    If there's no 'v##' suffix, version_str='' and version_num=0.
    """
    match = re.match(r'^(.*?)(v\d+)$', short_id)
    if match:
        base = match.group(1)
        version_str = match.group(2)
        # Convert 'v12' -> 12
        version_num = int(version_str[1:]) if version_str[1:].isdigit() else 0
    else:
        base = short_id
        version_str = ""
        version_num = 0
    return base, version_str, version_num

class ArxivPaperAgent(PassiveAPIAgent):
    """
    A passive agent that:
      - Periodically polls arXiv for newly published papers (descending by published date).
      - Only includes papers whose published date is within `time_window_days` of now.
      - On first sight of a base paper, checks it against a user-defined criteria function.
      - If a new version of a paper appears, we update the stored version if it's newer.
      - If the paper was in the active set, we keep it there; otherwise we skip re-checking.
      - On each poll, we prune out-of-window papers (published more than `time_window_days` ago).
      - *If we reset the criteria*, we *clear the active set* and *re-check everything in the cache
        still within the time window* under the new criteria, then poll again.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        criteria_func: Callable[[arxiv.Result], bool],
        time_window_days: int = 7,
        user_query: str = "",
        sort_by: arxiv.SortCriterion = arxiv.SortCriterion.SubmittedDate,
        sort_order: arxiv.SortOrder = arxiv.SortOrder.Descending
    ):
        """
        :param check_interval_seconds: Poll frequency in seconds.
        :param criteria_func: (arxiv.Result) -> bool, user-defined filter.
        :param time_window_days: Only keep papers published within this many days.
        :param user_query: If empty => 'all:all'; else used as an arXiv query string.
        :param sort_by: Sort criterion, default 'SubmittedDate' => published date.
        :param sort_order: Ascending/Descending, default descending => newest first.
        """
        super().__init__(check_interval_seconds)

        if not user_query.strip():
            user_query = "all:all"  # fallback to everything

        self.user_query = user_query
        self.criteria_func = criteria_func
        self.time_window_days = time_window_days
        self.sort_by = sort_by
        self.sort_order = sort_order

        # Paper cache: keyed by base ID, e.g. '2501.18595'.
        # Value: {
        #   "latest_version_str": "v2",
        #   "latest_version_num": 2,
        #   "data": <arxiv.Result of the latest version>,
        #   "published_naive_utc": datetime,
        #   "passed_criteria": bool
        # }
        self._paper_cache: Dict[str, Dict[str, Any]] = {}

        # Active set: set of base IDs that currently pass the criteria and are in-window.
        self._active_tracking_set: Set[str] = set()

        # Callback: invoked after every poll with a dict of all active items
        self.on_tracked_change: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        # Use a large max pagination to catch all relevant papers (arxiv supports up to ~300k).
        self._client = arxiv.Client(page_size=200, delay_seconds=0.5)

    async def handle_polling(self):
        """
        1) Build a search sorted by published date (descending), up to 300k.
        2) Iterate results: stop when we see a paper published before our cutoff.
        3) For each paper in-window:
            - Parse base ID
            - If new base ID => check criteria => store
            - If existing => update only if the version is strictly newer
        4) Prune out-of-window from the cache & active set.
        5) on_tracked_change(...) with a dict of all active items, marking those that changed.
        """
        logger.info("[ArxivPaperAgent] Polling arXiv...")

        changed_ids: Set[str] = set()
        cutoff_utc = datetime.utcnow() - timedelta(days=self.time_window_days)

        # Build a big search and iterate
        search = arxiv.Search(
            query=self.user_query,
            max_results=300000,
            sort_by=self.sort_by,
            sort_order=self.sort_order
        )

        results_iter = self._client.results(search)
        count_in_window = 0

        # Go newest first; break if we see a paper older than the cutoff
        for paper in results_iter:
            pub_naive = self._to_naive_utc(paper.published)
            if pub_naive < cutoff_utc:
                break  # out-of-window => stop reading further

            count_in_window += 1
            short_id = paper.get_short_id()
            base_id, ver_str, ver_num = extract_arxiv_base_and_version(short_id)

            if base_id not in self._paper_cache:
                # New base ID => apply criteria
                passed = self.criteria_func(paper)
                self._paper_cache[base_id] = {
                    "latest_version_str": ver_str,
                    "latest_version_num": ver_num,
                    "data": paper,
                    "published_naive_utc": pub_naive,
                    "passed_criteria": passed
                }
                if passed:
                    self._active_tracking_set.add(base_id)
                changed_ids.add(base_id)
            else:
                # If we already know this base paper, only update if new version
                info = self._paper_cache[base_id]
                if ver_num > info["latest_version_num"]:
                    # Strictly newer version => update record
                    info["latest_version_str"] = ver_str
                    info["latest_version_num"] = ver_num
                    info["data"] = paper
                    info["published_naive_utc"] = pub_naive
                    # If it was previously in active set, keep it there
                    # We don't re-check if it wasn't in active set.
                    changed_ids.add(base_id)

        logger.info(
            f"[ArxivPaperAgent] Stopped fetching after {count_in_window} in-window papers, "
            "either exhausted results or encountered out-of-window items."
        )

        # Prune out-of-window from cache
        to_remove = []
        for b_id, record in self._paper_cache.items():
            if record["published_naive_utc"] < cutoff_utc:
                to_remove.append(b_id)

        for b_id in to_remove:
            del self._paper_cache[b_id]
            if b_id in self._active_tracking_set:
                self._active_tracking_set.remove(b_id)
                changed_ids.add(b_id)

        # Build payload & invoke callback
        if self.on_tracked_change:
            payload = {}
            for b_id in self._active_tracking_set:
                rec = self._paper_cache[b_id]
                paper_obj = rec["data"]
                payload[b_id] = {
                    "data": paper_obj,
                    "published_iso": self._to_iso_8601_utc(paper_obj.published),
                    "updated_iso": self._to_iso_8601_utc(paper_obj.updated),
                    # The short ID for the latest version we know
                    "short_id": paper_obj.get_short_id(),
                    "just_changed": (b_id in changed_ids)
                }
            self.on_tracked_change(payload)

        logger.info(
            f"[ArxivPaperAgent] Poll complete. Cache size={len(self._paper_cache)}; "
            f"Active size={len(self._active_tracking_set)}; Changed this poll={len(changed_ids)}."
        )

    async def new_criteria_reset(self, new_criteria_func: Callable[[arxiv.Result], bool]):
        """
        Switch to a new criteria on-the-fly. We:
          1) Clear the existing active set.
          2) Remove from the cache any papers out of window (time_window_days).
          3) Re-check each *remaining* paper in the cache with new_criteria_func.
          4) Rebuild the active set from that new pass/fail result.
          5) Force an immediate poll to pick up newly published or new-version papers
             that might appear in the time window.
        """
        logger.info("[ArxivPaperAgent] new_criteria_reset called.")
        self.criteria_func = new_criteria_func

        # 1) Clear active set (we're going to re-check everything in the window from scratch)
        self._active_tracking_set.clear()

        # 2) Prune out-of-window items from the cache
        cutoff_utc = datetime.utcnow() - timedelta(days=self.time_window_days)
        to_remove = [
            b_id for b_id, record in self._paper_cache.items()
            if record["published_naive_utc"] < cutoff_utc
        ]
        for b_id in to_remove:
            del self._paper_cache[b_id]

        # 3) Re-check each remaining paper in the cache
        for b_id, record in self._paper_cache.items():
            paper_obj = record["data"]
            passed = self.criteria_func(paper_obj)
            record["passed_criteria"] = passed
            if passed:
                self._active_tracking_set.add(b_id)

        # 4) Force an immediate poll with the new criteria
        await self.handle_polling()

    def _to_naive_utc(self, dt_in: datetime) -> datetime:
        """
        Convert an offset-aware datetime to naive UTC, or leave if naive.
        """
        if dt_in.tzinfo is not None:
            return dt_in.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_in

    def _to_iso_8601_utc(self, dt_in: datetime) -> str:
        """
        Return an ISO 8601 UTC string (e.g. '2025-01-01T12:34:56Z').
        """
        if dt_in.tzinfo is None:
            dt_in = dt_in.replace(tzinfo=timezone.utc)
        else:
            dt_in = dt_in.astimezone(timezone.utc)
        return dt_in.isoformat().replace("+00:00", "Z")

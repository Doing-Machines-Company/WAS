# test_arxiv_agent.py

import asyncio
import logging
import arxiv

from arxiv_passive_agent import ArxivPaperAgent

logging.basicConfig(level=logging.INFO)

def sample_criteria(paper: arxiv.Result) -> bool:
    """
    Example: Return True if the title or summary contains 'computer science'.
    """
    text = (paper.title + " " + paper.summary).lower()
    return "computer science" in text

def quantum_criteria(paper: arxiv.Result) -> bool:
    """
    Another example: True if 'quant-ph' appears in categories.
    """
    return any("quant-ph" in cat.lower() for cat in paper.categories)

def on_tracked_change(changes):
    """
    changes = {
      "<base_id>": {
         "data": <arxiv.Result>,
         "published_iso": "2025-01-02T12:00:00Z",
         "updated_iso":   "2025-01-03T10:15:45Z",
         "short_id":      "2501.18595v2",
         "just_changed":  True/False
      },
      ...
    }
    """
    logging.info(f"[CALLBACK] Received {len(changes)} active paper(s).")
    changed = [bid for bid, info in changes.items() if info["just_changed"]]
    for base_id, info in changes.items():
        paper = info["data"]
        logging.info(
            f"  - BaseID={base_id}, short_id={info['short_id']}, "
            f"Title={paper.title!r}, just_changed={info['just_changed']}"
        )
    if changed:
        logging.info(f"[CALLBACK] The following base IDs changed this poll: {changed}")

async def main():
    # Poll every 30s, keep papers published in last 5 days, searching 'computer science' initially.
    agent = ArxivPaperAgent(
        check_interval_seconds=30,
        criteria_func=sample_criteria,
        time_window_days=5,
        user_query="computer science"
    )
    agent.on_tracked_change = on_tracked_change

    # Start agent in background
    task = asyncio.create_task(agent.start())

    # Let it run for ~1 minute => about two polls
    logging.info("[MAIN] Running agent with sample_criteria for ~1 minute.")
    await asyncio.sleep(60)

    # Switch to quantum_criteria
    logging.info("\n=== Switching to 'quantum_criteria' ===\n")
    await agent.new_criteria_reset(quantum_criteria)

    # Let it run for another 45s
    logging.info("[MAIN] Running agent with quantum_criteria for 45s.")
    await asyncio.sleep(45)

    # Stop agent
    agent.stop()
    await task

    logging.info("[MAIN] Agent stopped. Test complete.")

if __name__ == "__main__":
    asyncio.run(main())

# WAS

**WAS** (Web Agent Startup) was a research project and early-stage company building LLM agents that operate real websites end-to-end. This repo contains the full system from both phases of the project.

## Phase 1 — A faster web agent

Most browser agents at the time re-discovered every page from scratch on each run, which was slow and unreliable. WAS took a different approach: **learn the site once, then act fast**.

- **Site graph.** A scraper crawls a target site and builds a graph where nodes are pages (or page-states) and edges are the actions that move between them.
- **Offline labelling.** Each node and edge is labelled by an LLM using page screenshots + DOM, so the graph carries semantic descriptions ("this is the cart page", "this button adds a topping").
- **Runtime attachment.** When the agent is given a task, it doesn't re-explore — it plans over the pre-labelled graph and only falls back to live LLM reasoning when the page diverges from what's known.

The payoff was a meaningful speedup and reliability boost on long, multi-page flows.

### Demo — ordering on dominos.com

End-to-end run on Domino's: the agent takes a natural-language order and drives the site through item selection and checkout.

https://github.com/user-attachments/assets/b6f160d1-971e-48c1-a083-6cd7c1241604

## Phase 2 — Assignment tracker (inbound.fyi)

We pivoted the underlying agent stack into a product for students: an automatic assignment tracker.

- Pulls assignments from **Canvas** and **Gradescope** via their APIs.
- Syncs them into **Google Calendar** and **Google Tasks**.
- Surfaces everything in a custom dashboard hosted at [inbound.fyi](https://inbound.fyi).
- Optional **SMS interface** (Twilio) so users can ask about deadlines or trigger actions over text.

The API integrations live under [api_agent/](api_agent/); the browser-agent core lives in [UIAgent.py](UIAgent.py), [impls.py](impls.py), and the `scrape*` modules.

## Development Notes

- Requires Python 3.11.11
- Install dependencies: `pip install -r requirements.txt`

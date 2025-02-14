# README: PassiveAPIAgent

The **`PassiveAPIAgent`** is an **abstract base class** designed to manage recurring or “passive” polling loops in an asynchronous environment. Concrete subclasses of `PassiveAPIAgent` focus on specific data sources (e.g., Google Calendar events, Google Tasks, Gmail threads), but they all follow the same core pattern for starting, stopping, and performing periodic checks.

Below is a comprehensive overview of how `PassiveAPIAgent` works, what methods it provides, and what information is returned by it or required by subclasses.

---

## Table of Contents

1. [Core Purpose](#core-purpose)
2. [Key Methods](#key-methods)
3. [Lifecycle and Flow](#lifecycle-and-flow)
4. [Return Data & Active Set Callbacks](#return-data--active-set-callbacks)
5. [Implementing Subclasses](#implementing-subclasses)

---

## Core Purpose

At a high level, `PassiveAPIAgent`:

1. **Runs in a loop**—polling data sources periodically.
2. **Provides hooks** (`handle_polling`, `new_criteria_reset`, `on_tracked_change`) that subclasses implement to define custom logic.
3. **Manages an active or “tracked” set** of items that the subclass deems relevant (based on some user-defined criteria).
4. **Fires a callback** to supply the **entire** active set after every poll, noting which items changed in that specific poll.

---

## Key Methods

### 1. `__init__(self, check_interval_seconds: int = 60)`
**Purpose**: Constructor for the base class.
- **Parameters**:
  - `check_interval_seconds`: How often the polling loop will run (in seconds). Defaults to `60`.

### 2. `async def start(self)`
**Purpose**: **Entry point** for the agent’s main loop.
- Sleeps for `check_interval_seconds`, then calls the subclass’s `handle_polling()` method repeatedly.
- Continues until `stop()` is called.
- Logs informational messages about when it starts and stops.

### 3. `def stop(self)`
**Purpose**: Signals the agent to **cease** polling.
- Sets an internal `_stop_requested` flag.
- The `start()` loop checks this flag before each iteration.

### 4. `async def handle_polling(self)`
**Purpose**: **Abstract method**. Must be implemented by each subclass.
- Called automatically inside `start()` after each wait interval.
- Should contain the core “polling” or “retrieval” logic for that data source.
- Typically, after finishing its polling, the subclass invokes the callback (`on_tracked_change`) with the full active set.

### 5. `async def new_criteria_reset(self)`
**Purpose**: **Abstract method**. Must be implemented by each subclass.
- Allows external code to update the logic or filters used by the subclass.
- Often triggers an immediate poll so the subclass can adopt the new criteria right away.
- Many subclasses rebuild or modify their “active” set of tracked items in this method.

### 6. `async def on_tracked_change(self, changes: dict)`
**Purpose**: **Abstract method**. Must be implemented by each subclass.
- **Receives a dictionary** describing the current active set after a poll.
    - The current active set is ALL THE THINGS WE WANT ON THE UI from the criteria + website.
- The dictionary structure is typically:
  ```python
  {
    "<item_id>": {
      "data": <the_item_data_structure>,
      "just_changed": <bool>
    },
    ...
  }
  ```
- **`"data"`** contains the raw data for that tracked item (e.g., a calendar event, task details, etc.).
- **`"just_changed"`** is **True** if that item was created, updated, or deleted in the **most recent** poll, **False** otherwise.

Subclasses or user code can decide what to do upon receiving this dictionary—for example, logging, sending notifications, or storing data.

---

## Lifecycle and Flow

1. **Instantiation**: A subclass is created with a specified poll interval and any data-specific parameters.
2. **`start()`**:
   - Enters a loop: wait for `check_interval_seconds`, then call `handle_polling()`.
   - If an exception occurs, it’s logged; the loop continues unless stopped.
3. **`handle_polling()`** (subclass-implemented):
   - Gathers fresh data from the external source (e.g., calls an API).
   - Updates the local cache of items or an internal “active” set.
   - Fires **one** callback that includes **all** currently tracked items and flags which items changed.
4. **`on_tracked_change(changes: dict)`**:
   - The subclass’s callback is invoked automatically.
   - Typically logs or forwards these changes.
5. **`new_criteria_reset()`** (subclass-implemented, optional usage):
   - Allows dynamic updates to the criteria function or other filters.
   - In many cases, triggers a new poll so the agent can apply the new filtering logic immediately.
6. **`stop()`**:
   - Causes the main loop in `start()` to exit on its next iteration.
   - Allows the agent to gracefully shut down.

---

## Return Data & Active Set Callbacks

A **major feature** of `PassiveAPIAgent` is how it manages and returns an “active set” of items:

- **Active Set**: A collection of item IDs (or keys) that the subclass deems relevant.
  - Relevance is often defined by a **criteria function** (e.g., “title must contain ‘important’”).
  - Once an item meets criteria, many subclasses continue tracking it unless it is **explicitly removed** (e.g., if it’s deleted).

- **Callback Content**:
  - After **every** poll (`handle_polling()` call), the agent typically calls `on_tracked_change()` **once**.
  - This callback includes **all** items in the active set. Each item in the callback has:
    - `"data"`: The item’s detailed information (e.g., a dict from a JSON API).
    - `"just_changed"`: Whether that item changed in this poll cycle.

- **Reasoning**:
  - This design ensures the consumer always has a **complete snapshot** of the currently tracked items.
  - Simultaneously, the consumer can tell if any item is new, updated, or otherwise changed on each poll by checking `"just_changed"`.

---

## Implementing Subclasses

To create a working subclass:

1. **Inherit** from `PassiveAPIAgent`.
2. **Implement** `handle_polling()`:
   - Poll the data source (e.g., an API).
   - Update the internal active set and/or item cache as appropriate.
   - Build a dictionary of `{id: {"data": <item>, "just_changed": <bool>}, ...}` for all active items.
   - Call `self.on_tracked_change(your_dict)` if a callback is defined.

3. **Implement** `new_criteria_reset()`:
   - If your agent uses a user-defined filtering function, allow that function to be replaced.
   - Consider re-checking or re-polling data so the active set is consistent with the new criteria.

4. **Optionally** override `on_tracked_change(...)` if the subclass needs a default behavior. Or rely on users providing a callback function dynamically.

5. **Call** `start()` to run the polling loop, and `stop()` to halt it.

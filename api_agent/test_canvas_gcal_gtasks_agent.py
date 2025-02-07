# test_canvas_gcal_gtasks_agent.py

import asyncio
import logging

from agents.canvas.canvas_api_agent import CanvasAPIAgent
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent


logging.basicConfig(level=logging.INFO)

"""

import asyncio
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I have a birthday for James Chan on Feb 10."
    )
    asyncio.run(agent.run())


"""

async def main():
    # # Instantiate the Canvas agent
    # agent = CanvasAPIAgent()
    # print("Agent task:", agent.task)
    #
    # # Run the agent. It will loop, call the LLM for next actions, etc.
    # # You can stop it manually or let the STOP action from LLM end it.
    # await agent.run()
    #
    # # Optionally, do any post-run checks or prints
    # print("Agent run has completed.")
    # poll_out = agent.get_poll_output()
    #
    # input(poll_out)
    #
    # step_size = 1
    #
    # for i in range(0, len(poll_out), step_size):
    #     cur_chunk = poll_out[i:i + step_size]
    #     task_string = ""
    #     for i, linmem in enumerate(cur_chunk):
    #         task_string += f"{i})\nCall: \n{linmem.call}\nReceived: \n{linmem.received}\n"
    #     input(task_string)
    #     skip = input("SKIP?")
    #     if skip == "":
    #         agent = GCalGTasksAPIAgent(
    #             task=task_string,
    #             from_user=False
    #         )
    #         await agent.run()
    #     else:
    #         continue
    call = "canvas_list_assignments with parameters {'course_id': '36003', 'include': ['due_at', 'rubric', 'submission']}"
    # received = "[{'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 630236, 'name': 'Quiz 1', 'due_at': '2025-09-07T03:59:59Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 636844, 'name': 'Quiz 2', 'due_at': '2025-09-14T16:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 640241, 'name': 'Quiz 3', 'due_at': '2025-09-21T16:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 641508, 'name': 'Quiz 4', 'due_at': '2025-10-05T16:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 641511, 'name': 'Quiz 5', 'due_at': '2025-10-12T16:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 641527, 'name': 'Quiz 6', 'due_at': '2025-10-26T16:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 641525, 'name': 'Quiz 7', 'due_at': '2025-11-16T17:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 641526, 'name': 'Quiz 8', 'due_at': '2025-11-30T17:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 651877, 'name': 'Quiz 9', 'due_at': '2025-12-01T17:20:00Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610447, 'name': 'Exam I: Learning', 'due_at': '2025-09-28T03:59:00Z', 'points_possible': 200.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610449, 'name': 'Exam 2: Attention', 'due_at': '2025-11-06T17:20:00Z', 'points_possible': 200.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610438, 'name': 'Exam 3: Language and Higher Cognition ', 'due_at': '2025-12-06T17:20:00Z', 'points_possible': 200.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610452, 'name': 'Homework 1A', 'due_at': '2025-09-12T13:30:00Z', 'points_possible': 10.0, 'submission_types': ['none']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610446, 'name': 'Homework 1B', 'due_at': '2025-09-21T15:59:00Z', 'points_possible': 90.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610440, 'name': 'Homework 2', 'due_at': '2025-10-27T00:20:00Z', 'points_possible': 100.0, 'submission_types': ['online_quiz']}, {'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 610441, 'name': 'Homework 3', 'due_at': '2025-11-30T17:20:00Z', 'points_possible': 100.0, 'submission_types': ['online_quiz']}]"
    received = "[{'course name': '85211-A Cognitive Psychology (36003)', 'assignment id': 630236, 'name': 'Homework 1', 'due_at': '2025-09-07T03:59:59Z', 'points_possible': 50.0, 'submission_types': ['online_quiz']}]"

    task_string = f"1)\nCall: \n{call}\nReceived: \n{received}\n"

    agent = GCalGTasksAPIAgent(
        task=task_string,
        from_user=False
    )
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

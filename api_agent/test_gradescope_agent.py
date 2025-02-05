# from gradescopeapi.classes.connection import GSConnection
# from gradescopeapi.classes.extensions import get_extensions, update_student_extension
# # create connection and login
# connection = GSConnection()
# connection.login("cadatepe@andrew.cmu.edu", "Loltroll720^")

# """
# Fetching all courses for user
# """

# account = connection.account
# print(account)
# courses = account.get_courses()['student']
# for course_id, course_obj in courses.items():
#     print(f"{course_obj} (ID: {course_id})")
#     for assignment in account.get_assignments(course_id):
#         print(assignment)
#         try:
#             extensions = get_extensions(
#                 session=connection.session,
#                 course_id=str(course_id),
#                 assignment_id=str(assignment.assignment_id),
#             )
#             print(extensions)
#         except RuntimeError as e:
#             print(e)
# test_canvas_agent.py

import asyncio
import logging

from agents.gradescope.gradescope_api_agent import GradescopeAPIAgent 

logging.basicConfig(level=logging.INFO)


async def main():
    # Instantiate the Canvas agent
    agent = GradescopeAPIAgent()
    print("Agent task:", agent.task)

    # Run the agent. It will loop, call the LLM for next actions, etc.
    # You can stop it manually or let the STOP action from LLM end it.
    await agent.run()

    # Optionally, do any post-run checks or prints
    print("Agent run has completed.")


if __name__ == "__main__":
    asyncio.run(main())


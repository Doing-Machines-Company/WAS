import asyncio
import logging
import os
import json
from canvasapi import Canvas
from datetime import datetime, timezone 

credentials = None
if os.path.exists("canvas.json"):
    with open("canvas.json", "r") as credentials_file:
        # `credentials` is a dictionary with two keys: `url` and `token`
        credentials = json.load(credentials_file)

if not credentials:
    raise FileNotFoundError("Unable to find Canvas credentials file.")

service = Canvas(credentials["url"], credentials["token"])

course = service.get_course(36003, include=['syllabus_body'])
# print(course.syllabus_body)
page = course.show_front_page
# print(page)
# input()
# for page in course.get_assignments():
#     print(page)
# module = course.get_module(305559)
# for item in module.get_module_items():
#     print(item)
    
# print(f"Course name: {course.name}")
# print(f"Course homepage URL: {course.homepage_url}")


filter_date = datetime(2023, 11, 1, tzinfo=timezone.utc)
assignments = course.get_assignments()
filtered_assignments = []
for assignment in assignments:
    filtered_assignment = {
        'id': assignment.id,
        'name': assignment.name,
        'due_at': assignment.due_at,
        'points_possible': assignment.points_possible,
        'submission_types': assignment.submission_types
    }
    assignment_updated_at = datetime.strptime(assignment.updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if assignment_updated_at > filter_date:
        filtered_assignments.append(filtered_assignment)
print(filtered_assignments)

# for tab in course.get_tabs():
#     print(tab)
# print(course.syllabus_body)
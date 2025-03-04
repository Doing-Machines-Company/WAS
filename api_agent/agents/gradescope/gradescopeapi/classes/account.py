import time

from bs4 import BeautifulSoup

from agents.gradescope.gradescopeapi import DEFAULT_GRADESCOPE_BASE_URL
from agents.gradescope.gradescopeapi.classes._helpers._assignment_helpers import (
    check_page_auth,
    get_assignments_instructor_view,
    get_assignments_student_view,
    get_submission_files,
)
from agents.gradescope.gradescopeapi.classes._helpers._course_helpers import (
    get_course_members,
    get_courses_info,
)
from agents.gradescope.gradescopeapi.classes.assignments import Assignment
from agents.gradescope.gradescopeapi.classes.member import Member


import asyncio

class Account:
    def __init__(self, session, gradescope_base_url: str = DEFAULT_GRADESCOPE_BASE_URL):
        self.session = session
        self.gradescope_base_url = gradescope_base_url

    async def get_courses(self) -> dict:
        """
        Get all courses for the user, including both instructor and student courses.

        Returns:
            dict: A dictionary with keys "instructor" and "student", each mapping course IDs to Course objects.

        Raises:
            RuntimeError: If request to account page fails.
        """
        endpoint = f"{self.gradescope_base_url}/account"

        async with self.session.get(endpoint) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Failed to access account page on Gradescope. Status code: {response.status}"
                )
            response_text = await response.text()

        soup = BeautifulSoup(response_text, "html.parser")

        # Determine if the user is solely a student or instructor.
        user_courses, is_instructor = get_courses_info(soup, "Your Courses")

        if user_courses:
            if is_instructor:
                return {"instructor": user_courses, "student": {}}
            else:
                return {"instructor": {}, "student": user_courses}

        # If the user is both a student and instructor, get both sets of courses.
        courses = {"instructor": {}, "student": {}}

        instructor_courses, _ = get_courses_info(soup, "Instructor Courses")
        courses["instructor"] = instructor_courses

        student_courses, _ = get_courses_info(soup, "Student Courses")
        courses["student"] = student_courses

        return courses

    async def get_course_users(self, course_id: str) -> list:
        """
        Get a list of all users in a course.

        Returns:
            list: A list of Member objects representing the users in the course.
        Raises:
            Exception: If course_id is invalid or an error occurs during fetching.
        """
        membership_endpoint = f"{self.gradescope_base_url}/courses/{course_id}/memberships"

        if not course_id:
            raise Exception("Invalid Course ID")

        try:
            # Await the async helper that verifies page authorization.
            membership_resp = await check_page_auth(self.session, membership_endpoint)
            membership_text = await membership_resp.text()
            membership_soup = BeautifulSoup(membership_text, "html.parser")

            users = get_course_members(membership_soup, course_id)
            return users
        except Exception:
            return None

    async def get_assignments(self, course_id: str) -> list:
        """
        Get a list of detailed assignment information for a course.

        Returns:
            list: A list of Assignment objects.
        Raises:
            Exception: If course_id is invalid or an error occurs during fetching.
        """
        if not course_id:
            raise Exception("Invalid Course ID")

        course_endpoint = f"{self.gradescope_base_url}/courses/{course_id}"
        coursepage_text = await check_page_auth(self.session, course_endpoint)
        coursepage_soup = BeautifulSoup(coursepage_text, "html.parser")

        # Try instructor view first; if no assignments found, try student view.
        assignment_info_list = get_assignments_instructor_view(coursepage_soup)
        if not assignment_info_list:
            assignment_info_list = get_assignments_student_view(coursepage_soup)

        return assignment_info_list

    async def get_assignment_submissions(self, course_id: str, assignment_id: str) -> dict:
        """
        Get a dictionary mapping submission IDs to a list of AWS links for each submission.

        Returns:
            dict: Keys are submission IDs and values are lists of AWS links (strings).
        Raises:
            Exception: For invalid parameters or access issues.
        """
        if not course_id or not assignment_id:
            raise Exception("One or more invalid parameters")

        ASSIGNMENT_ENDPOINT = f"{self.gradescope_base_url}/courses/{course_id}/assignments/{assignment_id}"
        ASSIGNMENT_SUBMISSIONS_ENDPOINT = f"{ASSIGNMENT_ENDPOINT}/review_grades"

        submissions_resp = await check_page_auth(self.session, ASSIGNMENT_SUBMISSIONS_ENDPOINT)
        submissions_text = await submissions_resp.text()
        submissions_soup = BeautifulSoup(submissions_text, "html.parser")

        submissions_a_tags = submissions_soup.select("td.table--primaryLink a")
        submission_ids = [
            a_tag.attrs.get("href").split("/")[-1] for a_tag in submissions_a_tags
        ]

        submission_links = {}
        for submission_id in submission_ids:
            # Await the async helper to get submission files.
            aws_links = await get_submission_files(self.session, course_id, assignment_id, submission_id)
            submission_links[submission_id] = aws_links
            # Avoid sending too many requests too quickly.
            await asyncio.sleep(0.1)
        return submission_links

    async def get_assignment_submission(self, student_email: str, course_id: str, assignment_id: str) -> list:
        """
        Get AWS links to files of a student's most recent submission for an assignment.

        Returns:
            list: A list of AWS link strings.
        Raises:
            Exception: For invalid parameters or if no submission is found.
        """
        if not (student_email and course_id and assignment_id):
            raise Exception("One or more invalid parameters")

        ASSIGNMENT_ENDPOINT = f"{self.gradescope_base_url}/courses/{course_id}/assignments/{assignment_id}"
        ASSIGNMENT_SUBMISSIONS_ENDPOINT = f"{ASSIGNMENT_ENDPOINT}/review_grades"

        submissions_resp = await check_page_auth(self.session, ASSIGNMENT_SUBMISSIONS_ENDPOINT)
        submissions_text = await submissions_resp.text()
        submissions_soup = BeautifulSoup(submissions_text, "html.parser")

        td_with_email = submissions_soup.find("td", string=lambda s: student_email in str(s))
        if td_with_email:
            submission_td = td_with_email.find_previous_sibling()
            a_element = submission_td.find("a")
            if a_element:
                submission_id = a_element.get("href").split("/")[-1]
            else:
                raise Exception("No submission found")
            aws_links = await get_submission_files(self.session, course_id, assignment_id, submission_id)
            return aws_links
        else:
            raise Exception("No submission found")

    async def get_assignment_graders(self, course_id: str, question_id: str) -> set:
        """
        Get a set of graders for a specific question in an assignment.

        Returns:
            set: A set of grader names (strings).
        Raises:
            Exception: For invalid parameters or access issues.
        """
        if not course_id or not question_id:
            raise Exception("One or more invalid parameters")

        QUESTION_ENDPOINT = f"{self.gradescope_base_url}/courses/{course_id}/questions/{question_id}"
        ASSIGNMENT_SUBMISSIONS_ENDPOINT = f"{QUESTION_ENDPOINT}/submissions"

        submissions_resp = await check_page_auth(self.session, ASSIGNMENT_SUBMISSIONS_ENDPOINT)
        submissions_text = await submissions_resp.text()
        submissions_soup = BeautifulSoup(submissions_text, "html.parser")

        graders = submissions_soup.select("td")[2::3]
        grader_names = {grader.text for grader in graders if grader.text}
        return grader_names

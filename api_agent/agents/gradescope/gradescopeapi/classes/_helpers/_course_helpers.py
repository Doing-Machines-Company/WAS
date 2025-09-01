import json

from bs4 import BeautifulSoup

from agents.gradescope.gradescopeapi.classes.courses import Course
from agents.gradescope.gradescopeapi.classes.member import Member

def _parse_course_list_block(cl_block, semester, year):
    out = {}
    # iterate all course anchors within this block
    for a in cl_block.select("div.courseList--coursesForTerm > a.courseBox[href]"):
        href = (a.get("href") or "").rstrip("/")
        if not href.startswith("/courses/"):
            continue
        cid = href.split("/")[-1]
        short_el = a.select_one("h3.courseBox--shortname")
        full_el  = a.select_one("div.courseBox--name")
        assign_el = a.select_one("div.courseBox--assignments")
        grades_el = a.select_one("div.courseBox--noGradesPublished, div.courseBox--gradesPublished")
        out[cid] = {
            "name": short_el.get_text(strip=True) if short_el else "",
            "full_name": full_el.get_text(strip=True) if full_el else "",
            "semester": semester,
            "year": year,
            "num_assignments": assign_el.get_text(strip=True) if assign_el else None,
            "num_grades_published": grades_el.get_text(strip=True) if grades_el else None,
        }
    return out

def get_courses_info(soup: BeautifulSoup, section_title: str | None = None) -> tuple[dict[str, Course], bool]:
    """
    Parse the Gradescope account page.
    If section_title is given, it must be exactly 'Instructor Courses' or 'Student Courses'.
    Returns (courses_by_id, is_instructor_for_this_parse)
    """
    all_courses: dict[str, Course] = {}
    root = soup.select_one("#account-show") or soup

    # Map each courseList to its nearest previous h2.pageHeading
    blocks = []
    for cl in root.select("div.courseList"):
        prev_h2 = cl.find_previous("h2", class_="pageHeading")
        title = prev_h2.get_text(strip=True) if prev_h2 else ""
        blocks.append((title, cl))

    # Fallback: single block pages with empty/absent heading
    if not blocks:
        cl = root.select_one("div.courseList")
        if not cl:
            return {}, False
        blocks = [("", cl)]

    # Filter by requested section, if provided
    if section_title:
        blocks = [(t, cl) for (t, cl) in blocks if t == section_title]
        if not blocks:
            return {}, (section_title.lower().startswith("instructor") if section_title else False)

    is_instructor = False
    for title, cl in blocks:
        this_is_instructor = title.lower().startswith("instructor")
        is_instructor = is_instructor or this_is_instructor

        # iterate each term within this block
        for term_div in cl.select("div.courseList--term"):
            term_txt = term_div.get_text(strip=True)
            parts = term_txt.split()
            semester, year = (parts[0], parts[1]) if len(parts) >= 2 else (term_txt, "")

            courses_for_term = term_div.find_next_sibling("div", class_="courseList--coursesForTerm")
            if not courses_for_term:
                continue

            parsed = _parse_course_list_block(courses_for_term, semester, year)
            for cid, ci in parsed.items():
                all_courses[cid] = Course(
                    name=ci["name"],
                    full_name=ci["full_name"],
                    semester=ci["semester"],
                    year=ci["year"],
                    num_assignments=ci["num_assignments"],
                    num_grades_published=ci["num_grades_published"] if this_is_instructor else None,
                )

    return all_courses, is_instructor

def get_course_members(soup: BeautifulSoup, course_id: str) -> list[Member]:
    """
    Scrape all course members from the membership page of a Gradescope course.

    Args:
        soup (BeautifulSoup): BeautifulSoup object with parsed HTML.
        course_id (str): The course ID to which the members belong.

    Returns:
        List: A list of Member objects containing all course members' info.

        For example:
        [
            Member(...),
            Member(...)
        ]
    """

    member_list = []

    # maps role id to role name
    id_to_role = {"0": "Student", "1": "Instructor", "2": "TA", "3": "Reader"}

    # find all rows with class rosterRow (each row is a member)
    roster_rows = soup.find_all("tr", class_="rosterRow")

    for row in roster_rows:
        # get all table data for each row
        cells = row.find_all("td")

        # get data from first cell
        cell = cells[0]

        data_button = cell.find("button", class_="rosterCell--editIcon")

        # fetch full name from data-cm attribute in button
        data_cm = data_button.get("data-cm")
        json_data_cm = json.loads(data_cm)  # convert to json
        full_name = json_data_cm.get("full_name")

        # fetch LMS related attributes
        first_name = json_data_cm.get("first_name")
        last_name = json_data_cm.get("last_name")
        sid = json_data_cm.get("sid")

        # fetch other attributes: email, id, role, and section
        # from data attributes in button
        email = data_button.get("data-email")
        id = data_button.get("data-id")
        role = id_to_role[data_button.get("data-role")]
        sections = data_button.get("data-sections")  # TODO: check if this is correct

        # fetch number of submissions from 4th cell
        num_submissions = int(cells[3].text)

        # create Member object with all relevant info
        member = Member(
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            sid=sid,
            email=email,
            role=role,
            id=id,
            num_submissions=num_submissions,
            sections=sections,
            course_id=course_id,
        )

        member_list.append(member)

    return member_list

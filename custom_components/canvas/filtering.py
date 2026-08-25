"""Noise filtering and data cleansing heuristics engine for Canvas LMS."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .const import (
    ACTIVE_ENROLLMENT_STATES,
    COMPLETED_TERM_STATES,
    DEFAULT_STALE_DAYS_THRESHOLD,
    FILTER_NOT_GRADED,
)
from .models import CanvasAssignment, CanvasCourse


def _to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC-aware datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_active_course(course: CanvasCourse, now: datetime | None = None) -> bool:
    """Return True if course belongs to an active, current academic term.

    Discards unnamed courses, non-available courses, inactive enrollments,
    and courses whose term/course end date is in the past.
    """
    current_time = _to_utc(now) or datetime.now(timezone.utc)

    # 1. Filter out empty or placeholder course names
    if (
        not course.name
        or course.name.strip() in ("", "Unnamed Course", "None")
        or (course.name.startswith("Course ") and course.name[7:].isdigit())
    ):
        return False

    # 2. Check workflow state
    if course.workflow_state != "available":
        return False

    # 3. Check enrollment states (if enrollments are provided)
    if course.enrollments:
        if not any(
            e.enrollment_state in ACTIVE_ENROLLMENT_STATES for e in course.enrollments
        ):
            return False

    # 4. Check term end date and workflow state
    if course.term is not None:
        if course.term.workflow_state in COMPLETED_TERM_STATES:
            return False
        if course.term.end_at is not None:
            term_end = _to_utc(course.term.end_at)
            if term_end is not None and term_end < current_time:
                return False

    # 5. Check course end date
    if course.end_at is not None:
        course_end = _to_utc(course.end_at)
        if course_end is not None and course_end < current_time:
            return False

    return True


def filter_active_courses(
    courses: list[CanvasCourse],
    now: datetime | None = None,
) -> list[CanvasCourse]:
    """Filter a list of courses down to only active courses."""
    return [c for c in courses if is_active_course(c, now=now)]


def is_active_todo_assignment(
    assignment: CanvasAssignment,
    course: CanvasCourse,
    now: datetime | None = None,
) -> bool:
    """Return True if assignment is an actionable, pending task for the student.

    Discards non-graded placeholders, pre-term cloned syllabus templates,
    and already assessed/excused items.
    """
    current_time = _to_utc(now) or datetime.now(timezone.utc)

    # 0. Reject assignments not belonging to this course
    if assignment.course_id != 0 and assignment.course_id != course.id:
        return False

    # 1. Workflow state check
    if assignment.workflow_state != "published":
        return False

    # 2. Non-graded & zero point placeholder filtering
    if assignment.grading_type == FILTER_NOT_GRADED:
        return False
    if FILTER_NOT_GRADED in assignment.submission_types:
        return False
    if assignment.points_possible == 0.0 and assignment.omit_from_final_grade:
        return False

    # 3. Reject future locked assignments
    if assignment.unlock_at is not None:
        unlock_time = _to_utc(assignment.unlock_at)
        if unlock_time is not None and unlock_time > current_time:
            return False

    # 4. Term start date boundary (Cloned template filtering)
    term_start: datetime | None = None
    if course.term and course.term.start_at:
        term_start = _to_utc(course.term.start_at)
    elif course.start_at:
        term_start = _to_utc(course.start_at)

    if (due_time := _to_utc(assignment.due_at)) is not None:
        if term_start is not None:
            if due_time < term_start:
                # Assignment due date predates term start
                return False
        else:
            # Fallback when term start date is missing: discard stale historical dates
            stale_boundary = current_time - timedelta(days=DEFAULT_STALE_DAYS_THRESHOLD)
            if due_time < stale_boundary:
                return False

    # 5. Graded or excused exclusion
    if assignment.submission is not None and assignment.submission.is_graded_or_excused:
        return False

    return True


def filter_pending_assignments(
    assignments: list[CanvasAssignment],
    course: CanvasCourse,
    now: datetime | None = None,
) -> list[CanvasAssignment]:
    """Filter assignments to only pending, actionable items for a course."""
    return [a for a in assignments if is_active_todo_assignment(a, course, now=now)]

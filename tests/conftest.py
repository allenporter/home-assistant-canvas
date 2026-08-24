"""Fixtures for the Canvas LMS custom component tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.canvas.const import DOMAIN

CONF_BASE_URL = "base_url"
CONF_ACCESS_TOKEN = "access_token"

TEST_BASE_URL = "https://canvas.example.edu"
TEST_ACCESS_TOKEN = "mock_access_token_12345"
TEST_USER_ID = 12345
TEST_USER_NAME = "Allen Porter"

# Sample API JSON responses
MOCK_USER_SELF_RESPONSE: dict[str, Any] = {
    "id": TEST_USER_ID,
    "name": TEST_USER_NAME,
    "sortable_name": "Porter, Allen",
    "short_name": "Allen",
    "primary_email": "allen@example.edu",
    "created_at": "2026-08-24T00:00:00Z",
}

MOCK_OBSERVEES_RESPONSE: list[dict[str, Any]] = [
    {
        "id": 6021,
        "name": "Quentin Porter",
        "sortable_name": "Porter, Quentin",
        "short_name": "Quentin",
        "pronouns": "He/Him",
        "observation_link_root_account_ids": [1],
    },
    {
        "id": 4899,
        "name": "Theodore Porter",
        "sortable_name": "Porter, Theodore",
        "short_name": "Theodore",
        "pronouns": "He/Him",
        "observation_link_root_account_ids": [1],
    },
]

MOCK_COURSES_RESPONSE: list[dict[str, Any]] = [
    {
        "id": 7349,
        "name": "AP US History",
        "course_code": "APUSH-101",
        "account_id": 142,
        "start_at": "2026-08-15T00:00:00Z",
        "end_at": "2026-12-20T23:59:59Z",
        "workflow_state": "available",
        "term": {
            "id": 413,
            "name": "Fall 2026",
            "start_at": "2026-08-15T00:00:00Z",
            "end_at": "2026-12-20T23:59:59Z",
            "workflow_state": "active",
        },
        "teachers": [
            {
                "id": 4857,
                "display_name": "Dr. Jon Asoulin",
                "avatar_image_url": "https://canvas.example.edu/avatar.png",
                "html_url": "https://canvas.example.edu/teachers/4857",
                "pronouns": "He/Him",
            }
        ],
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "role_id": 3,
                "user_id": 6021,
                "enrollment_state": "active",
                "computed_current_score": 92.5,
                "computed_current_grade": "A-",
                "computed_final_score": 88.0,
                "computed_final_grade": "B+",
                "current_period_computed_current_score": 92.5,
                "current_period_computed_current_grade": "A-",
                "current_grading_period_title": "Semester 1",
            }
        ],
    }
]

MOCK_SUBMISSIONS_RESPONSE: list[dict[str, Any]] = [
    {
        "id": 5196766,
        "assignment_id": 134664,
        "user_id": 6021,
        "workflow_state": "unsubmitted",
        "grade": None,
        "score": None,
        "excused": False,
        "missing": False,
        "late": False,
        "submitted_at": None,
        "graded_at": None,
        "submission_type": "online_text_entry",
        "assignment": {
            "id": 134664,
            "course_id": 7349,
            "name": "Chapter 1 Reflection",
            "description": "<p>Write reflection on Chapter 1</p>",
            "due_at": "2026-09-01T23:59:59Z",
            "lock_at": "2026-09-05T23:59:59Z",
            "unlock_at": "2026-08-20T00:00:00Z",
            "points_possible": 10.0,
            "grading_type": "points",
            "submission_types": ["online_text_entry"],
            "omit_from_final_grade": False,
            "workflow_state": "published",
            "html_url": "https://canvas.example.edu/courses/7349/assignments/134664",
        },
    }
]


def build_mock_user_dict(
    user_id: int = TEST_USER_ID,
    name: str = TEST_USER_NAME,
    primary_email: str | None = "allen@example.edu",
    sortable_name: str | None = "Porter, Allen",
    short_name: str | None = "Allen",
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas user dictionary."""
    data: dict[str, Any] = {
        "id": user_id,
        "name": name,
        "sortable_name": sortable_name,
        "short_name": short_name,
        "primary_email": primary_email,
    }
    data.update(extra)
    return data


def build_mock_observee_dict(
    observee_id: int = 6021,
    name: str = "Quentin Porter",
    sortable_name: str | None = "Porter, Quentin",
    short_name: str | None = "Quentin",
    pronouns: str | None = "He/Him",
    root_account_ids: list[int] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas observee dictionary."""
    data: dict[str, Any] = {
        "id": observee_id,
        "name": name,
        "sortable_name": sortable_name,
        "short_name": short_name,
        "pronouns": pronouns,
        "observation_link_root_account_ids": (
            root_account_ids if root_account_ids is not None else [1]
        ),
    }
    data.update(extra)
    return data


def build_mock_term_dict(
    term_id: int = 413,
    name: str = "Fall 2026",
    start_at: str | None = "2026-08-15T00:00:00Z",
    end_at: str | None = "2026-12-20T23:59:59Z",
    workflow_state: str = "active",
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas term dictionary."""
    data: dict[str, Any] = {
        "id": term_id,
        "name": name,
        "start_at": start_at,
        "end_at": end_at,
        "workflow_state": workflow_state,
    }
    data.update(extra)
    return data


def build_mock_teacher_dict(
    teacher_id: int = 4857,
    display_name: str = "Dr. Jon Asoulin",
    avatar_image_url: str | None = "https://canvas.example.edu/avatar.png",
    html_url: str | None = "https://canvas.example.edu/teachers/4857",
    pronouns: str | None = "He/Him",
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas teacher dictionary."""
    data: dict[str, Any] = {
        "id": teacher_id,
        "display_name": display_name,
        "avatar_image_url": avatar_image_url,
        "html_url": html_url,
        "pronouns": pronouns,
    }
    data.update(extra)
    return data


def build_mock_course_dict(
    course_id: int = 7349,
    name: str = "AP US History",
    course_code: str | None = "APUSH-101",
    account_id: int | None = 142,
    start_at: str | None = "2026-08-15T00:00:00Z",
    end_at: str | None = "2026-12-20T23:59:59Z",
    workflow_state: str = "available",
    term: dict[str, Any] | None = None,
    teachers: list[dict[str, Any]] | None = None,
    enrollments: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas course dictionary."""
    data: dict[str, Any] = {
        "id": course_id,
        "name": name,
        "course_code": course_code,
        "account_id": account_id,
        "start_at": start_at,
        "end_at": end_at,
        "workflow_state": workflow_state,
        "term": term if term is not None else build_mock_term_dict(),
        "teachers": teachers if teachers is not None else [build_mock_teacher_dict()],
        "enrollments": enrollments if enrollments is not None else [],
    }
    data.update(extra)
    return data


def build_mock_submission_dict(
    submission_id: int = 5196766,
    assignment_id: int = 134664,
    user_id: int = 6021,
    workflow_state: str = "unsubmitted",
    grade: str | None = None,
    score: float | None = None,
    excused: bool = False,
    missing: bool = False,
    late: bool = False,
    submitted_at: str | None = None,
    graded_at: str | None = None,
    submission_type: str | None = "online_text_entry",
    assignment: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas submission dictionary."""
    data: dict[str, Any] = {
        "id": submission_id,
        "assignment_id": assignment_id,
        "user_id": user_id,
        "workflow_state": workflow_state,
        "grade": grade,
        "score": score,
        "excused": excused,
        "missing": missing,
        "late": late,
        "submitted_at": submitted_at,
        "graded_at": graded_at,
        "submission_type": submission_type,
    }
    if assignment is not None:
        data["assignment"] = assignment
    data.update(extra)
    return data


def build_mock_assignment_dict(
    assignment_id: int = 134664,
    course_id: int = 7349,
    name: str = "Chapter 1 Reflection",
    description: str | None = "<p>Write reflection on Chapter 1</p>",
    due_at: str | None = "2026-09-01T23:59:59Z",
    lock_at: str | None = "2026-09-05T23:59:59Z",
    unlock_at: str | None = "2026-08-20T00:00:00Z",
    points_possible: float | None = 10.0,
    grading_type: str | None = "points",
    submission_types: list[str] | None = None,
    omit_from_final_grade: bool = False,
    workflow_state: str = "published",
    html_url: str | None = "https://canvas.example.edu/courses/7349/assignments/134664",
    submission: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a mock Canvas assignment dictionary."""
    data: dict[str, Any] = {
        "id": assignment_id,
        "course_id": course_id,
        "name": name,
        "description": description,
        "due_at": due_at,
        "lock_at": lock_at,
        "unlock_at": unlock_at,
        "points_possible": points_possible,
        "grading_type": grading_type,
        "submission_types": (
            submission_types if submission_types is not None else ["online_text_entry"]
        ),
        "omit_from_final_grade": omit_from_final_grade,
        "workflow_state": workflow_state,
        "html_url": html_url,
    }
    if submission is not None:
        data["submission"] = submission
    data.update(extra)
    return data


def build_link_header(
    *,
    current_url: str | None = None,
    next_url: str | None = None,
    prev_url: str | None = None,
    first_url: str | None = None,
    last_url: str | None = None,
) -> str:
    """Build an RFC 5988 Link header for pagination testing."""
    links: list[str] = []
    if current_url:
        links.append(f'<{current_url}>; rel="current"')
    if next_url:
        links.append(f'<{next_url}>; rel="next"')
    if prev_url:
        links.append(f'<{prev_url}>; rel="prev"')
    if first_url:
        links.append(f'<{first_url}>; rel="first"')
    if last_url:
        links.append(f'<{last_url}>; rel="last"')
    return ", ".join(links)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Enable custom integration."""
    _ = enable_custom_integrations
    yield


@pytest.fixture(name="mock_config_entry")
def fixture_mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Fixture to create a mock Canvas configuration entry."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: TEST_BASE_URL,
            CONF_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
        },
        unique_id=str(TEST_USER_ID),
        title=TEST_USER_NAME,
        version=1,
        minor_version=1,
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture(name="config_entry")
def fixture_config_entry(mock_config_entry: MockConfigEntry) -> MockConfigEntry:
    """Alias for mock_config_entry."""
    return mock_config_entry


@pytest.fixture(name="platforms")
def mock_platforms() -> list[Platform]:
    """Fixture for platforms loaded by the integration."""
    return []

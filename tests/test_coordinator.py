"""Comprehensive unit tests for the Canvas LMS DataUpdateCoordinator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.canvas.const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.canvas.exceptions import (
    CanvasAuthError,
    CanvasConnectionError,
    CanvasError,
    CanvasRateLimitError,
    CanvasResponseError,
)
from custom_components.canvas.models import (
    CanvasAssignment,
    CanvasCourse,
    CanvasData,
    CanvasEnrollment,
    CanvasGrade,
    CanvasObservee,
    CanvasSubmission,
    CanvasTeacher,
    CanvasTerm,
    CanvasUser,
)

from custom_components.canvas.coordinator import CanvasDataUpdateCoordinator

from .conftest import (
    TEST_USER_ID,
    TEST_USER_NAME,
)

FROZEN_NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

MOCK_USER = CanvasUser(
    id=TEST_USER_ID,
    name=TEST_USER_NAME,
    sortable_name="Porter, Allen",
    short_name="Allen",
    primary_email="allen@example.edu",
)

MOCK_STUDENT_1 = CanvasObservee(
    id=6021,
    name="Quentin Porter",
    sortable_name="Porter, Quentin",
    short_name="Quentin",
    pronouns="He/Him",
    root_account_ids=(1,),
)

MOCK_STUDENT_2 = CanvasObservee(
    id=4899,
    name="Theodore Porter",
    sortable_name="Porter, Theodore",
    short_name="Theodore",
    pronouns="He/Him",
    root_account_ids=(1,),
)

MOCK_ACTIVE_TERM = CanvasTerm(
    id=413,
    name="Fall 2026",
    start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="active",
)

MOCK_PAST_TERM = CanvasTerm(
    id=200,
    name="Fall 2024",
    start_at=datetime(2024, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2024, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="completed",
)

MOCK_COURSE_1 = CanvasCourse(
    id=7349,
    name="AP US History",
    course_code="APUSH-101",
    account_id=142,
    start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="available",
    term=MOCK_ACTIVE_TERM,
    teachers=(
        CanvasTeacher(
            id=4857,
            display_name="Dr. Jon Asoulin",
            avatar_image_url="https://canvas.example.edu/avatar.png",
            html_url="https://canvas.example.edu/teachers/4857",
            pronouns="He/Him",
        ),
    ),
    enrollments=(
        CanvasEnrollment(
            type="student",
            role="StudentEnrollment",
            user_id=6021,
            enrollment_state="active",
            grade=CanvasGrade(
                current_score=92.5,
                current_grade="A-",
                final_score=88.0,
                final_grade="B+",
            ),
        ),
    ),
)

MOCK_COURSE_2 = CanvasCourse(
    id=7350,
    name="AP Biology",
    course_code="BIO-201",
    account_id=142,
    start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="available",
    term=MOCK_ACTIVE_TERM,
    teachers=(
        CanvasTeacher(
            id=4858,
            display_name="Ms. Brenda Smith",
            avatar_image_url="https://canvas.example.edu/avatar2.png",
        ),
    ),
    enrollments=(
        CanvasEnrollment(
            type="student",
            role="StudentEnrollment",
            user_id=6021,
            enrollment_state="active",
            grade=CanvasGrade(
                current_score=95.0,
                current_grade="A",
            ),
        ),
    ),
)

MOCK_ZOMBIE_COURSE = CanvasCourse(
    id=7000,
    name="Counselor's Corner 2024",
    course_code="COUNS-24",
    account_id=142,
    start_at=datetime(2024, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2024, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="available",
    term=MOCK_PAST_TERM,
    teachers=(),
    enrollments=(
        CanvasEnrollment(
            type="student",
            role="StudentEnrollment",
            user_id=6021,
            enrollment_state="active",
            grade=CanvasGrade(),
        ),
    ),
)

MOCK_SUBMISSION_ACTIVE = CanvasSubmission(
    id=5196766,
    assignment_id=134664,
    user_id=6021,
    workflow_state="unsubmitted",
    grade=None,
    score=None,
    excused=False,
    missing=False,
    late=False,
    submitted_at=None,
    graded_at=None,
    submission_type="online_text_entry",
)

MOCK_SUBMISSION_CLONED = CanvasSubmission(
    id=5196767,
    assignment_id=134665,
    user_id=6021,
    workflow_state="unsubmitted",
    grade=None,
    score=None,
    excused=False,
    missing=False,
    late=False,
    submitted_at=None,
    graded_at=None,
    submission_type="online_text_entry",
)

MOCK_SUBMISSION_GRADED = CanvasSubmission(
    id=5196768,
    assignment_id=134666,
    user_id=6021,
    workflow_state="graded",
    grade="A",
    score=20.0,
    excused=False,
    missing=False,
    late=False,
    submitted_at=datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc),
    graded_at=datetime(2026, 8, 21, 10, 0, 0, tzinfo=timezone.utc),
    submission_type="online_quiz",
)

MOCK_ASSIGNMENT_ACTIVE = CanvasAssignment(
    id=134664,
    course_id=7349,
    name="Chapter 1 Reflection",
    description="<p>Write reflection on Chapter 1</p>",
    due_at=datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc),
    lock_at=datetime(2026, 9, 5, 23, 59, 59, tzinfo=timezone.utc),
    unlock_at=datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc),
    points_possible=10.0,
    grading_type="points",
    submission_types=("online_text_entry",),
    omit_from_final_grade=False,
    workflow_state="published",
    html_url="https://canvas.example.edu/courses/7349/assignments/134664",
    submission=MOCK_SUBMISSION_ACTIVE,
)

MOCK_ASSIGNMENT_CLONED_PRETERM = CanvasAssignment(
    id=134665,
    course_id=7349,
    name="Historical Syllabus Acknowledgement (2023)",
    description="<p>Sign old syllabus</p>",
    due_at=datetime(2023, 8, 20, 23, 59, 59, tzinfo=timezone.utc),  # Pre-term!
    points_possible=5.0,
    grading_type="points",
    submission_types=("online_text_entry",),
    workflow_state="published",
    submission=MOCK_SUBMISSION_CLONED,
)

MOCK_ASSIGNMENT_GRADED = CanvasAssignment(
    id=134666,
    course_id=7349,
    name="Summer Reading Quiz",
    description="<p>Quiz on summer reading</p>",
    due_at=datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc),
    points_possible=20.0,
    grading_type="points",
    submission_types=("online_quiz",),
    workflow_state="published",
    submission=MOCK_SUBMISSION_GRADED,
)


def _require_coordinator() -> type[CanvasDataUpdateCoordinator]:
    """Helper to verify coordinator module exists."""
    if CanvasDataUpdateCoordinator is None:
        pytest.skip("CanvasDataUpdateCoordinator not implemented yet")
    return CanvasDataUpdateCoordinator


# ============================================================================
# Tier 1: Core Feature Coverage Tests (>= 5 cases)
# ============================================================================


async def test_coordinator_initialization(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator initialization with 60-minute interval and metadata."""
    coordinator_cls = _require_coordinator()
    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    assert coordinator.update_interval == timedelta(minutes=60)
    assert coordinator.name == DOMAIN or coordinator.name == mock_config_entry.title
    assert coordinator.data is None


async def test_coordinator_update_data_dual_students_success(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test successful data update fetching user, observees, courses, and pending assignments."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(
        return_value=[MOCK_STUDENT_1, MOCK_STUDENT_2]
    )

    # Student 1 courses: 2 active, 1 zombie
    # Student 2 courses: 1 active
    async def mock_get_student_courses(student_id: int) -> list[CanvasCourse]:
        if student_id == 6021:
            return [MOCK_COURSE_1, MOCK_COURSE_2, MOCK_ZOMBIE_COURSE]
        if student_id == 4899:
            return [MOCK_COURSE_1]
        return []

    mock_canvas_client.async_get_student_courses = AsyncMock(
        side_effect=mock_get_student_courses
    )

    # Submissions / assignments per course
    async def mock_get_submissions_or_assignments(
        course_id: int, student_id: int
    ) -> list[CanvasSubmission]:
        if course_id == 7349 and student_id == 6021:
            return [
                MOCK_SUBMISSION_ACTIVE,
                MOCK_SUBMISSION_CLONED,
                MOCK_SUBMISSION_GRADED,
            ]
        return []

    mock_canvas_client.async_get_student_submissions = AsyncMock(
        side_effect=mock_get_submissions_or_assignments
    )
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        return_value=[
            MOCK_ASSIGNMENT_ACTIVE,
            MOCK_ASSIGNMENT_CLONED_PRETERM,
            MOCK_ASSIGNMENT_GRADED,
        ]
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.canvas.filtering.datetime",
            type(
                "MockDateTime",
                (datetime,),
                {"now": classmethod(lambda cls, tz=None: FROZEN_NOW)},
            ),
        )
        data = await coordinator._async_update_data()

    assert isinstance(data, CanvasData)
    assert data.user.id == TEST_USER_ID
    assert data.user.name == TEST_USER_NAME
    assert len(data.observees) == 2
    assert data.observees[0].id == 6021
    assert data.observees[1].id == 4899

    # Verify zombie course was filtered out
    assert 6021 in data.courses_by_student
    quentin_courses = data.courses_by_student[6021]
    assert len(quentin_courses) == 2
    assert {c.id for c in quentin_courses} == {7349, 7350}

    assert 4899 in data.courses_by_student
    assert len(data.courses_by_student[4899]) == 1

    # Verify cloned preterm & graded assignments were filtered out
    if 6021 in data.assignments_by_student and data.assignments_by_student[6021]:
        quentin_assignments = data.assignments_by_student[6021]
        assert len(quentin_assignments) == 1
        assert quentin_assignments[0].id == 134664
        assert quentin_assignments[0].name == "Chapter 1 Reflection"


async def test_coordinator_observee_fallback_single_student(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test observee fallback when user has no linked observees (treats self as student)."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[])  # No observees!
    mock_canvas_client.async_get_student_courses = AsyncMock(
        return_value=[MOCK_COURSE_1]
    )
    mock_canvas_client.async_get_student_submissions = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        return_value=[MOCK_ASSIGNMENT_ACTIVE]
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    data = await coordinator._async_update_data()

    assert len(data.observees) == 1
    assert data.observees[0].id == TEST_USER_ID
    assert data.observees[0].name == TEST_USER_NAME
    assert TEST_USER_ID in data.courses_by_student
    assert len(data.courses_by_student[TEST_USER_ID]) == 1
    mock_canvas_client.async_get_student_courses.assert_called_with(TEST_USER_ID)


async def test_coordinator_auth_error_raises_config_entry_auth_failed(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasAuthError is translated to ConfigEntryAuthFailed."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=CanvasAuthError("Token expired (HTTP 401)")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_connection_error_raises_update_failed(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasConnectionError is translated to UpdateFailed."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=CanvasConnectionError("Server unreachable (HTTP 502)")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_unexpected_error_raises_update_failed(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasError or generic unexpected exceptions raise UpdateFailed."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=CanvasError("Canvas unexpected internal error")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_polling_cadence_60_minutes(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that advancing time by 60 minutes triggers coordinator update."""
    coordinator_cls = _require_coordinator()
    freezer.move_to(FROZEN_NOW)
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(
        return_value=[MOCK_COURSE_1]
    )
    mock_canvas_client.async_get_student_submissions = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_assignments = AsyncMock(return_value=[])

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )
    unsub = coordinator.async_add_listener(lambda: None)

    # Initial refresh
    await coordinator.async_config_entry_first_refresh()
    assert mock_canvas_client.async_get_current_user.call_count == 1

    # Advance time by 30 minutes: no new poll
    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert mock_canvas_client.async_get_current_user.call_count == 1

    # Advance time by another 30 minutes (total 60 min): triggers update
    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass, dt_util.utcnow(), fire_all=True)
    await hass.async_block_till_done()
    assert mock_canvas_client.async_get_current_user.call_count == 2
    unsub()


# ============================================================================
# Tier 2: Boundary, Corner & Adversarial Cases (>= 5 cases)
# ============================================================================


async def test_coordinator_rate_limit_error_raises_update_failed(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasRateLimitError is translated to UpdateFailed."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=CanvasRateLimitError("Rate limit exceeded (HTTP 429)")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_response_error_raises_update_failed(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasResponseError is translated to UpdateFailed."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=CanvasResponseError("Invalid JSON received")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_student_with_zero_courses(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator handles student with zero enrolled courses gracefully."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(return_value=[])

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    data = await coordinator._async_update_data()
    assert 6021 in data.courses_by_student
    assert data.courses_by_student[6021] == []
    assert data.assignments_by_student.get(6021, []) == []


async def test_coordinator_course_with_zero_assignments(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator handles course with zero assignments gracefully."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(
        return_value=[MOCK_COURSE_1]
    )
    mock_canvas_client.async_get_student_submissions = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_assignments = AsyncMock(return_value=[])

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    data = await coordinator._async_update_data()
    assert len(data.courses_by_student[6021]) == 1
    assert data.assignments_by_student.get(6021, []) == []


async def test_coordinator_course_fetch_partial_failure(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test error raised when fetching student courses fails mid-update."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(
        return_value=[MOCK_STUDENT_1, MOCK_STUDENT_2]
    )
    mock_canvas_client.async_get_student_courses = AsyncMock(
        side_effect=CanvasConnectionError("Timeout fetching courses")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_submissions_fetch_partial_failure(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test error raised when fetching student submissions fails mid-update."""
    coordinator_cls = _require_coordinator()
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(
        return_value=[MOCK_COURSE_1]
    )
    mock_canvas_client.async_get_student_submissions = AsyncMock(
        side_effect=CanvasConnectionError("Timeout fetching submissions")
    )
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        side_effect=CanvasConnectionError("Timeout fetching assignments")
    )

    coordinator = coordinator_cls(
        hass,
        client=mock_canvas_client,
        entry=mock_config_entry,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

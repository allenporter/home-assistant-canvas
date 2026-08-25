"""Comprehensive unit and integration tests for Canvas LMS Calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.canvas.calendar import CanvasCalendarEntity
from custom_components.canvas.const import (
    DOMAIN,
    ENDPOINT_COURSE_STUDENT_SUBMISSIONS,
    ENDPOINT_USER_COURSES,
    ENDPOINT_USERS_OBSERVEES,
    ENDPOINT_USERS_SELF,
)

from .conftest import (
    MOCK_OBSERVEES_RESPONSE,
    MOCK_USER_SELF_RESPONSE,
    TEST_BASE_URL,
    TEST_USER_ID,
)


def _setup_dual_student_routes(
    aioclient_mock: AiohttpClientMocker,
    apush_due: str = "2026-09-01T23:59:59Z",
    bio_due: str = "2026-09-05T20:00:00Z",
) -> None:
    """Set up fake Canvas API routes for two students with courses and assignments."""
    course_apush: dict[str, Any] = {
        "id": 7349,
        "name": "AP US History",
        "course_code": "APUSH-101",
        "workflow_state": "available",
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 6021,
                "enrollment_state": "active",
            }
        ],
    }

    course_bio: dict[str, Any] = {
        "id": 7350,
        "name": "Biology 1",
        "course_code": "BIO-201",
        "workflow_state": "available",
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 4899,
                "enrollment_state": "active",
            }
        ],
    }

    sub_apush: dict[str, Any] = {
        "id": 881,
        "user_id": 6021,
        "assignment_id": 134664,
        "workflow_state": "unsubmitted",
        "assignment": {
            "id": 134664,
            "name": "Chapter 1 Reflection",
            "course_id": 7349,
            "due_at": apush_due,
            "points_possible": 25.0,
            "description": "Read Chapter 1 and submit reflections.",
            "html_url": "https://canvas.example.edu/courses/7349/assignments/134664",
        },
    }

    sub_bio: dict[str, Any] = {
        "id": 882,
        "user_id": 4899,
        "assignment_id": 134665,
        "workflow_state": "unsubmitted",
        "assignment": {
            "id": 134665,
            "name": "Cell Structure Lab",
            "course_id": 7350,
            "due_at": bio_due,
            "points_possible": 50.0,
            "description": "Microscope observations.",
            "html_url": "https://canvas.example.edu/courses/7350/assignments/134665",
        },
    }

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=MOCK_OBSERVEES_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=6021)}",
        json=[course_apush],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        json=[sub_apush],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=4899)}",
        json=[course_bio],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7350)}",
        json=[sub_bio],
    )


async def test_calendar_entities_and_device_registry_dual_students(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting up calendar entities linked to student devices."""
    future_date_quentin = (dt_util.now() + timedelta(days=2)).replace(microsecond=0)
    future_iso_quentin = future_date_quentin.isoformat()
    future_date_theodore = (dt_util.now() + timedelta(days=5)).replace(microsecond=0)
    future_iso_theodore = future_date_theodore.isoformat()

    _setup_dual_student_routes(
        aioclient_mock,
        apush_due=future_iso_quentin,
        bio_due=future_iso_theodore,
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify device registry linking
    device_quentin = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_6021")}
    )
    assert device_quentin is not None
    assert device_quentin.name == "Quentin Porter"

    quentin_entity_id = entity_registry.async_get_entity_id(
        Platform.CALENDAR, DOMAIN, f"{mock_config_entry.unique_id}_6021_calendar"
    )
    assert quentin_entity_id == "calendar.quentin_porter_assignments"

    state_quentin = hass.states.get(quentin_entity_id)
    assert state_quentin is not None
    assert (
        state_quentin.attributes.get("message")
        == "[AP US History] Chapter 1 Reflection"
    )
    assert state_quentin.attributes.get("location") == "AP US History"
    assert "Read Chapter 1" in state_quentin.attributes.get("description", "")
    assert "Points: 25.0" in state_quentin.attributes.get("description", "")
    assert "URL: https://canvas.example.edu" in state_quentin.attributes.get(
        "description", ""
    )

    # Verify Theodore's calendar
    theodore_entity_id = entity_registry.async_get_entity_id(
        Platform.CALENDAR, DOMAIN, f"{mock_config_entry.unique_id}_4899_calendar"
    )
    assert theodore_entity_id == "calendar.theodore_porter_assignments"

    state_theodore = hass.states.get(theodore_entity_id)
    assert state_theodore is not None
    assert state_theodore.attributes.get("message") == "[Biology 1] Cell Structure Lab"


async def test_calendar_async_get_events_date_range_queries(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test async_get_events querying across various date ranges."""
    apush_due = datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc)
    _setup_dual_student_routes(aioclient_mock, apush_due=apush_due.isoformat())

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity = hass.data["entity_components"]["calendar"].get_entity(
        "calendar.quentin_porter_assignments"
    )
    assert isinstance(entity, CanvasCalendarEntity)

    # 1. Window covering the assignment
    events = await entity.async_get_events(
        hass,
        start_date=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 2, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    event = events[0]
    assert event.summary == "[AP US History] Chapter 1 Reflection"
    assert event.start == apush_due
    assert event.end == apush_due + timedelta(minutes=30)
    assert event.location == "AP US History"
    assert event.uid == "134664"

    # 2. Window strictly before the assignment
    events_before = await entity.async_get_events(
        hass,
        start_date=datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 8, 31, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert len(events_before) == 0

    # 3. Window strictly after the assignment
    events_after = await entity.async_get_events(
        hass,
        start_date=datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 20, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert len(events_after) == 0


async def test_calendar_next_upcoming_event_filtering(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test next upcoming event property logic with past and future assignments."""
    past_due = (dt_util.now() - timedelta(days=3)).replace(microsecond=0)
    _setup_dual_student_routes(aioclient_mock, apush_due=past_due.isoformat())

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity = hass.data["entity_components"]["calendar"].get_entity(
        "calendar.quentin_porter_assignments"
    )
    assert isinstance(entity, CanvasCalendarEntity)

    # When all assignments are past, event is None
    assert entity.event is None


async def test_calendar_assignment_without_due_date_or_course_metadata(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test handling assignments without due date, description, or course mapping."""
    sub_undated: dict[str, Any] = {
        "id": 883,
        "user_id": 6021,
        "assignment_id": 134666,
        "workflow_state": "unsubmitted",
        "assignment": {
            "id": 134666,
            "name": "Undated Syllabus Quiz",
            "course_id": 7349,
            "due_at": None,
        },
    }

    sub_minimal: dict[str, Any] = {
        "id": 884,
        "user_id": 6021,
        "assignment_id": 134667,
        "workflow_state": "unsubmitted",
        "assignment": {
            "id": 134667,
            "name": "Minimal Assignment",
            "course_id": 7349,
            "due_at": "2026-09-02T12:00:00Z",
            "description": None,
            "points_possible": None,
            "html_url": None,
        },
    }

    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=[MOCK_OBSERVEES_RESPONSE[0]],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=6021)}",
        json=[{"id": 7349, "name": "AP US History", "workflow_state": "available"}],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        json=[sub_undated, sub_minimal],
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity = hass.data["entity_components"]["calendar"].get_entity(
        "calendar.quentin_porter_assignments"
    )
    assert isinstance(entity, CanvasCalendarEntity)

    events = await entity.async_get_events(
        hass,
        start_date=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 3, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].summary == "[AP US History] Minimal Assignment"
    assert events[0].description is None
    assert events[0].location == "AP US History"

    # Simulate course removal to test fallback without course prefix or location
    coordinator = mock_config_entry.runtime_data
    coordinator.data.courses_by_student[6021] = ()
    events_unmapped = await entity.async_get_events(
        hass,
        start_date=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 3, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert len(events_unmapped) == 1
    assert events_unmapped[0].summary == "Minimal Assignment"
    assert events_unmapped[0].location is None


async def test_calendar_single_student_fallback_direct_login(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test single student direct login creates calendar entity linked to user profile."""
    future_date = (dt_util.now() + timedelta(days=1)).replace(microsecond=0)
    sub_math: dict[str, Any] = {
        "id": 885,
        "user_id": TEST_USER_ID,
        "assignment_id": 134668,
        "workflow_state": "unsubmitted",
        "assignment": {
            "id": 134668,
            "name": "Homework 1",
            "course_id": 7353,
            "due_at": future_date.isoformat(),
        },
    }

    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=[],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=TEST_USER_ID)}",
        json=[{"id": 7353, "name": "Algebra II", "workflow_state": "available"}],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7353)}",
        json=[sub_math],
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_{TEST_USER_ID}")}
    )
    assert device is not None
    assert device.name == "Allen Porter"

    entity_id = entity_registry.async_get_entity_id(
        Platform.CALENDAR,
        DOMAIN,
        f"{mock_config_entry.unique_id}_{TEST_USER_ID}_calendar",
    )
    assert entity_id == "calendar.allen_porter_assignments"

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("message") == "[Algebra II] Homework 1"


def _extract_events(response: Any, entity_id: str) -> list[dict[str, Any]]:
    """Extract event list from a calendar service response dictionary."""
    if not isinstance(response, dict):
        return []
    entity_data = response.get(entity_id, {})
    if not isinstance(entity_data, dict):
        return []
    events = entity_data.get("events", [])
    return list(events) if isinstance(events, list) else []


async def test_calendar_service_call_get_events(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test querying calendar via Home Assistant calendar.get_events service call."""
    apush_due = datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc)
    _setup_dual_student_routes(aioclient_mock, apush_due=apush_due.isoformat())

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": ["calendar.quentin_porter_assignments"],
            "start_date_time": "2026-09-01T00:00:00Z",
            "end_date_time": "2026-09-02T00:00:00Z",
        },
        blocking=True,
        return_response=True,
    )
    events = _extract_events(response, "calendar.quentin_porter_assignments")
    assert len(events) == 1
    assert events[0]["summary"] == "[AP US History] Chapter 1 Reflection"

"""Comprehensive unit and integration tests for Canvas LMS Sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import PERCENTAGE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.canvas.const import (
    DOMAIN,
    ENDPOINT_COURSE_STUDENT_SUBMISSIONS,
    ENDPOINT_USER_COURSES,
    ENDPOINT_USERS_OBSERVEES,
    ENDPOINT_USERS_SELF,
)
from custom_components.canvas.sensor import CanvasCourseGradeSensor

from .conftest import (
    MOCK_OBSERVEES_RESPONSE,
    MOCK_USER_SELF_RESPONSE,
    TEST_BASE_URL,
    TEST_USER_ID,
)


def _setup_dual_student_routes(
    aioclient_mock: AiohttpClientMocker,
    quentin_score: float = 94.5,
    quentin_letter: str = "A",
) -> None:
    """Set up standard fake Canvas API routes for two students with courses and submissions."""
    course_apush: dict[str, Any] = {
        "id": 7349,
        "name": "AP US History",
        "course_code": "APUSH-101",
        "workflow_state": "available",
        "term": {"id": 10, "name": "Fall 2026", "workflow_state": "active"},
        "teachers": [
            {
                "id": 901,
                "display_name": "Dr. Smith",
                "avatar_image_url": "https://canvas.instructure.com/images/smith.png",
            }
        ],
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 6021,
                "enrollment_state": "active",
                "computed_current_score": quentin_score,
                "computed_current_grade": quentin_letter,
                "computed_final_score": 92.0,
                "computed_final_grade": "A-",
                "current_period_computed_current_score": 95.0,
                "current_period_computed_current_grade": "A",
                "current_grading_period_title": "Quarter 1",
            }
        ],
    }

    course_bio: dict[str, Any] = {
        "id": 7350,
        "name": "Biology 1",
        "course_code": "BIO-201",
        "workflow_state": "available",
        "term": {"id": 10, "name": "Fall 2026", "workflow_state": "active"},
        "teachers": [
            {
                "id": 902,
                "display_name": "Mrs. Davis",
            }
        ],
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 4899,
                "enrollment_state": "active",
                "computed_current_score": 88.0,
                "computed_current_grade": "B+",
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
            "due_at": "2026-09-01T23:59:59Z",
            "points_possible": 25.0,
            "description": "Read Chapter 1 and submit reflections.",
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
            "due_at": "2026-09-05T20:00:00Z",
            "points_possible": 50.0,
            "description": "Microscope observations.",
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


async def test_sensor_entities_and_device_registry_dual_students(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that setting up config entry creates course grade sensors linked to student devices."""
    _setup_dual_student_routes(aioclient_mock)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify device registry linking for Quentin
    device_quentin = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_6021")}
    )
    assert device_quentin is not None
    assert device_quentin.name == "Quentin Porter"

    # Verify entity registry for Quentin's APUSH grade sensor
    quentin_entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{mock_config_entry.unique_id}_6021_7349_grade"
    )
    assert quentin_entity_id == "sensor.quentin_porter_ap_us_history_grade"

    state_quentin = hass.states.get(quentin_entity_id)
    assert state_quentin is not None
    assert state_quentin.state == "94.5"
    assert state_quentin.attributes.get("unit_of_measurement") == PERCENTAGE
    assert state_quentin.attributes.get("state_class") == SensorStateClass.MEASUREMENT
    assert state_quentin.attributes.get("icon") == "mdi:school"
    assert state_quentin.attributes.get("letter_grade") == "A"
    assert state_quentin.attributes.get("final_score") == 92.0
    assert state_quentin.attributes.get("final_grade") == "A-"
    assert state_quentin.attributes.get("current_period_score") == 95.0
    assert state_quentin.attributes.get("current_period_grade") == "A"
    assert state_quentin.attributes.get("grading_period_title") == "Quarter 1"
    assert state_quentin.attributes.get("course_id") == 7349
    assert state_quentin.attributes.get("course_name") == "AP US History"
    assert state_quentin.attributes.get("course_code") == "APUSH-101"
    assert state_quentin.attributes.get("instructor") == "Dr. Smith"
    assert state_quentin.attributes.get("term") == "Fall 2026"
    assert state_quentin.attributes.get("pending_assignments_count") == 1

    # Verify Theodore's Biology sensor
    theodore_entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{mock_config_entry.unique_id}_4899_7350_grade"
    )
    assert theodore_entity_id == "sensor.theodore_porter_biology_1_grade"

    state_theodore = hass.states.get(theodore_entity_id)
    assert state_theodore is not None
    assert state_theodore.state == "88.0"
    assert state_theodore.attributes.get("letter_grade") == "B+"
    assert state_theodore.attributes.get("instructor") == "Mrs. Davis"


async def test_sensor_course_with_missing_or_none_grade(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test handling courses with no computed score / grade gracefully."""
    course_art: dict[str, Any] = {
        "id": 7351,
        "name": "Studio Art",
        "workflow_state": "available",
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 6021,
                "enrollment_state": "active",
                "computed_current_score": None,
                "computed_current_grade": None,
            }
        ],
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
        json=[course_art],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7351)}",
        json=[],
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{mock_config_entry.unique_id}_6021_7351_grade"
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state in ("unknown", "unavailable", "None")
    assert state.attributes.get("course_name") == "Studio Art"
    assert "letter_grade" not in state.attributes


async def test_sensor_course_with_missing_teacher_or_term(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test handling courses without teachers, term, or course code."""
    course_homeroom: dict[str, Any] = {
        "id": 7352,
        "name": "Homeroom",
        "workflow_state": "available",
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": 6021,
                "enrollment_state": "active",
                "computed_current_score": 100.0,
                "computed_current_grade": "A+",
            }
        ],
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
        json=[course_homeroom],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7352)}",
        json=[],
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{mock_config_entry.unique_id}_6021_7352_grade"
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "100.0"
    assert "instructor" not in state.attributes
    assert "term" not in state.attributes
    assert "course_code" not in state.attributes


async def test_sensor_single_student_fallback_direct_login(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test single student direct login creates sensor linked to user profile."""
    course_math: dict[str, Any] = {
        "id": 7353,
        "name": "Algebra II",
        "course_code": "MATH-202",
        "workflow_state": "available",
        "enrollments": [
            {
                "type": "student",
                "role": "StudentEnrollment",
                "user_id": TEST_USER_ID,
                "enrollment_state": "active",
                "computed_current_score": 91.2,
                "computed_current_grade": "A-",
            }
        ],
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
        json=[course_math],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7353)}",
        json=[],
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_{TEST_USER_ID}")}
    )
    assert device is not None
    assert device.name == "Allen Porter"

    entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR,
        DOMAIN,
        f"{mock_config_entry.unique_id}_{TEST_USER_ID}_7353_grade",
    )
    assert entity_id == "sensor.allen_porter_algebra_ii_grade"

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "91.2"
    assert state.attributes.get("letter_grade") == "A-"


async def test_sensor_coordinator_update_and_removal(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sensor value updates on coordinator refresh and fallback if course removed."""
    _setup_dual_student_routes(aioclient_mock, quentin_score=94.5, quentin_letter="A")

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{mock_config_entry.unique_id}_6021_7349_grade"
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "94.5"

    # Update coordinator with new score
    _setup_dual_student_routes(aioclient_mock, quentin_score=97.8, quentin_letter="A+")
    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "97.8"
    assert state.attributes.get("letter_grade") == "A+"

    # Get the sensor entity instance directly and test fallback when course is absent
    sensor_entity = hass.data["entity_components"]["sensor"].get_entity(entity_id)
    assert isinstance(sensor_entity, CanvasCourseGradeSensor)
    assert sensor_entity.native_value == 97.8

    # Simulate student having multiple courses in coordinator to exercise search loop
    from custom_components.canvas.models import CanvasCourse

    dummy_other_course = CanvasCourse(id=99999, name="Other Course")
    matching_course = CanvasCourse(id=7349, name="AP US History")
    coordinator.data.courses_by_student[6021] = (dummy_other_course, matching_course)
    assert sensor_entity._get_current_course() == matching_course

    # Simulate course removal in coordinator data
    coordinator.data.courses_by_student[6021] = ()
    assert sensor_entity.native_value is None
    assert sensor_entity.extra_state_attributes == {"course_id": 7349}

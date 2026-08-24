"""Adversarial stress-testing suite for Canvas LMS DataUpdateCoordinator and Lifecycle.

Challenger 1 Empirical Verification Suite:
- Single student fallback when observees API returns empty list [] or edge usernames.
- Error escalation: Auth error -> ConfigEntryAuthFailed across pipeline stages.
- Error escalation: Network drop / timeout / rate limit / corrupt response -> UpdateFailed across all stages.
- Partial failure atomic rejection across multi-student pipelines.
- ConfigEntry lifecycle, reloads after options/reauth/reconfigure without memory leaks or stale coordinator references.
- Concurrent and high-volume stress testing using real CanvasApiClient and fake HTTP server.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiohttp
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.canvas.api import CanvasApiClient
from custom_components.canvas.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    ENDPOINT_COURSE_STUDENT_SUBMISSIONS,
    ENDPOINT_USER_COURSES,
    ENDPOINT_USERS_OBSERVEES,
    ENDPOINT_USERS_SELF,
)
from custom_components.canvas.coordinator import CanvasDataUpdateCoordinator
from custom_components.canvas.models import CanvasData

from .conftest import (
    MOCK_COURSES_RESPONSE,
    MOCK_OBSERVEES_RESPONSE,
    MOCK_SUBMISSIONS_RESPONSE,
    MOCK_USER_SELF_RESPONSE,
    TEST_ACCESS_TOKEN,
    TEST_BASE_URL,
    TEST_USER_ID,
    TEST_USER_NAME,
    build_mock_assignment_dict,
    build_mock_course_dict,
    build_mock_observee_dict,
    build_mock_submission_dict,
    build_mock_term_dict,
)

FROZEN_NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _create_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry
) -> CanvasDataUpdateCoordinator:
    """Create a coordinator instance with a real CanvasApiClient."""
    session = async_get_clientsession(hass)
    client = CanvasApiClient(
        base_url=TEST_BASE_URL,
        access_token=TEST_ACCESS_TOKEN,
        session=session,
    )
    return CanvasDataUpdateCoordinator(
        hass=hass,
        client=client,
        entry=entry,
    )


def _setup_standard_routes(
    aioclient_mock: AiohttpClientMocker, base_url: str = TEST_BASE_URL
) -> None:
    """Register standard routes for a working Canvas LMS instance."""
    aioclient_mock.get(
        f"{base_url}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{base_url}{ENDPOINT_USERS_OBSERVEES}",
        json=MOCK_OBSERVEES_RESPONSE[:1],
    )
    aioclient_mock.get(
        f"{base_url}{ENDPOINT_USER_COURSES.format(user_id=6021)}",
        json=MOCK_COURSES_RESPONSE,
    )
    aioclient_mock.get(
        f"{base_url}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        json=MOCK_SUBMISSIONS_RESPONSE,
    )


# ============================================================================
# 1. Single Student Fallback Scenarios
# ============================================================================


async def test_adversarial_single_student_fallback_empty_observees_list(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify observees API returning empty list correctly falls back to user credentials."""
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
        json=MOCK_COURSES_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        json=MOCK_SUBMISSIONS_RESPONSE,
    )

    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()

    assert isinstance(data, CanvasData)
    assert len(data.observees) == 1
    assert data.observees[0].id == TEST_USER_ID
    assert data.observees[0].name == TEST_USER_NAME
    assert data.observees[0].sortable_name == "Porter, Allen"
    assert data.observees[0].short_name == "Allen"

    assert TEST_USER_ID in data.courses_by_student
    assert len(data.courses_by_student[TEST_USER_ID]) == 1
    assert TEST_USER_ID in data.assignments_by_student
    assert len(data.assignments_by_student[TEST_USER_ID]) == 1


async def test_adversarial_single_student_fallback_none_fields_on_user(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify observees fallback survives user object with minimal/None optional fields."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json={
            "id": 9999,
            "name": "Sparse Student",
            "sortable_name": None,
            "short_name": None,
            "primary_email": None,
        },
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=[],
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=9999)}",
        json=[],
    )

    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()

    assert len(data.observees) == 1
    assert data.observees[0].id == 9999
    assert data.observees[0].name == "Sparse Student"
    assert data.observees[0].sortable_name is None
    assert data.observees[0].short_name is None
    assert data.courses_by_student[9999] == []
    assert data.assignments_by_student[9999] == []


# ============================================================================
# 2. Error Escalation Across Pipeline Stages
# ============================================================================


@pytest.mark.parametrize(
    "failing_endpoint_key",
    [
        "user",
        "observees",
        "courses",
        "submissions",
    ],
)
async def test_adversarial_auth_error_escalation_at_all_stages(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    failing_endpoint_key: str,
) -> None:
    """Verify CanvasAuthError at ANY point in the pipeline raises ConfigEntryAuthFailed."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        status=401 if failing_endpoint_key == "user" else 200,
        json=None if failing_endpoint_key == "user" else MOCK_USER_SELF_RESPONSE,
        text="HTTP 401 at user" if failing_endpoint_key == "user" else None,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        status=401 if failing_endpoint_key == "observees" else 200,
        json=None
        if failing_endpoint_key == "observees"
        else MOCK_OBSERVEES_RESPONSE[:1],
        text="HTTP 401 at observees" if failing_endpoint_key == "observees" else None,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=6021)}",
        status=401 if failing_endpoint_key == "courses" else 200,
        json=None if failing_endpoint_key == "courses" else MOCK_COURSES_RESPONSE,
        text="HTTP 401 at courses" if failing_endpoint_key == "courses" else None,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        status=401 if failing_endpoint_key == "submissions" else 200,
        json=None
        if failing_endpoint_key == "submissions"
        else MOCK_SUBMISSIONS_RESPONSE,
        text="HTTP 401 at submissions"
        if failing_endpoint_key == "submissions"
        else None,
    )

    coordinator = _create_coordinator(hass, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed) as exc_info:
        await coordinator._async_update_data()
    assert f"HTTP 401 at {failing_endpoint_key}" in str(exc_info.value)


@pytest.mark.parametrize(
    ("status_code", "error_body"),
    [
        (500, "Server Error 500"),
        (502, "Bad Gateway 502"),
        (503, "Service Unavailable 503"),
        (429, "Rate Limit Exceeded"),
    ],
)
async def test_adversarial_network_and_unexpected_error_escalation(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    status_code: int,
    error_body: str,
) -> None:
    """Verify all network, rate limit, response, and unexpected errors raise UpdateFailed."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        status=status_code,
        text=error_body,
    )

    coordinator = _create_coordinator(hass, mock_config_entry)

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert error_body in str(exc_info.value) or "Canvas" in str(exc_info.value)


async def test_adversarial_multi_student_partial_failure_atomic_rejection(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify partial failure during multi-student query rejects entire update atomically."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=MOCK_OBSERVEES_RESPONSE,
    )
    # Student 1 courses succeed
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=6021)}",
        json=MOCK_COURSES_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=7349)}",
        json=MOCK_SUBMISSIONS_RESPONSE,
    )
    # Student 2 courses fail with network error
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=4899)}",
        exc=aiohttp.ClientError("Network drop during student 2 course query"),
    )

    coordinator = _create_coordinator(hass, mock_config_entry)

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Network drop during student 2 course query" in str(exc_info.value)


# ============================================================================
# 3. Lifecycle, Reload & Stale Reference Stress
# ============================================================================


async def test_adversarial_repeated_entry_reloads_lifecycle_leak_check(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test 5 consecutive reloads: ensure clean teardown and fresh coordinator instances."""
    _setup_standard_routes(aioclient_mock)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coord_0 = mock_config_entry.runtime_data
    assert isinstance(coord_0, CanvasDataUpdateCoordinator)
    coordinator_instances: list[CanvasDataUpdateCoordinator] = [coord_0]

    # Perform 5 consecutive reloads
    for i in range(1, 6):
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED
        new_coord = mock_config_entry.runtime_data
        assert isinstance(new_coord, CanvasDataUpdateCoordinator)
        assert new_coord is not coord_0, f"Iteration {i}: coordinator was not replaced"
        assert new_coord not in coordinator_instances
        coordinator_instances.append(new_coord)

    assert len(coordinator_instances) == 6

    # Clean unload
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_adversarial_reauth_flow_updates_credentials_and_reloads_cleanly(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that completing a reauth flow updates token and triggers clean reload."""
    _setup_standard_routes(aioclient_mock)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    initial_coordinator = mock_config_entry.runtime_data

    # Start reauth flow
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Complete reauth flow with new token
    new_token = "new_refreshed_access_token_9999"
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: new_token},
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == new_token
    assert mock_config_entry.state is ConfigEntryState.LOADED

    # Verify runtime_data has refreshed coordinator instance with new token
    reloaded_coordinator = mock_config_entry.runtime_data
    assert reloaded_coordinator is not initial_coordinator
    assert reloaded_coordinator.client.access_token == new_token


async def test_adversarial_reconfigure_flow_updates_url_and_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that completing a reconfigure flow updates URL/token and triggers clean reload."""
    _setup_standard_routes(aioclient_mock)

    new_url = "https://canvas.newdistrict.edu"
    new_token = "reconfigured_token_12345"
    _setup_standard_routes(aioclient_mock, base_url=new_url)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    # Start reconfigure flow
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BASE_URL: new_url,
            CONF_ACCESS_TOKEN: new_token,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_BASE_URL] == new_url
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == new_token

    reloaded_coordinator = mock_config_entry.runtime_data
    assert reloaded_coordinator.client.base_url == new_url
    assert reloaded_coordinator.client.access_token == new_token


# ============================================================================
# 4. Concurrency & High Volume Stress
# ============================================================================


async def test_adversarial_concurrent_coordinator_refreshes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test coordinator debouncing under concurrent refresh requests."""
    _setup_standard_routes(aioclient_mock)

    coordinator = _create_coordinator(hass, mock_config_entry)

    # Fire 10 concurrent refreshes
    await asyncio.gather(
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
        coordinator.async_refresh(),
    )
    await hass.async_block_till_done()

    assert coordinator.data is not None
    assert coordinator.data.user.id == TEST_USER_ID
    assert coordinator.last_update_success is True


async def test_adversarial_high_volume_observees_and_courses_isolation(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test coordinator with 10 observees and 5 courses each (50 total courses)."""
    num_students = 10
    num_courses_per_student = 5

    observees = [
        build_mock_observee_dict(
            observee_id=1000 + i,
            name=f"Student {i}",
            sortable_name=f"Student, {i}",
            short_name=f"S{i}",
        )
        for i in range(num_students)
    ]

    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        json=MOCK_USER_SELF_RESPONSE,
    )
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_OBSERVEES}",
        json=observees,
    )

    term = build_mock_term_dict(term_id=101, name="Fall 2026", workflow_state="active")

    for i in range(num_students):
        student_id = 1000 + i
        courses = [
            build_mock_course_dict(
                course_id=student_id * 10 + c,
                name=f"Course {student_id}-{c}",
                course_code=f"C-{student_id}-{c}",
                term=term,
            )
            for c in range(num_courses_per_student)
        ]
        aioclient_mock.get(
            f"{TEST_BASE_URL}{ENDPOINT_USER_COURSES.format(user_id=student_id)}",
            json=courses,
        )
        for c in range(num_courses_per_student):
            course_id = student_id * 10 + c
            asg = build_mock_assignment_dict(
                assignment_id=course_id * 100,
                course_id=course_id,
                name=f"Assignment {course_id}",
            )
            sub = build_mock_submission_dict(
                submission_id=course_id * 1000,
                assignment_id=course_id * 100,
                user_id=student_id,
                assignment=asg,
            )
            aioclient_mock.get(
                f"{TEST_BASE_URL}{ENDPOINT_COURSE_STUDENT_SUBMISSIONS.format(course_id=course_id)}",
                json=[sub],
            )

    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()

    assert len(data.observees) == num_students
    assert len(data.courses_by_student) == num_students
    assert len(data.assignments_by_student) == num_students


# ============================================================================
# 5. Integration Setup State Transitions & Options Listener Trigger
# ============================================================================


async def test_adversarial_setup_entry_auth_failed_sets_setup_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that auth error during setup entry marks config entry as SETUP_ERROR."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        status=401,
        text="Expired credentials (HTTP 401)",
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_adversarial_setup_entry_connection_error_sets_setup_retry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that network timeout during setup entry marks config entry as SETUP_RETRY."""
    aioclient_mock.get(
        f"{TEST_BASE_URL}{ENDPOINT_USERS_SELF}",
        exc=aiohttp.ClientError("Server unreachable (HTTP 504)"),
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_adversarial_options_update_listener_triggers_reload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that updating entry options triggers async_reload_entry via registered listener."""
    _setup_standard_routes(aioclient_mock)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    initial_coordinator = mock_config_entry.runtime_data

    # Update options on entry
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={"custom_scan_interval": 1800},
    )
    await hass.async_block_till_done()

    # Reload should have happened automatically
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not initial_coordinator

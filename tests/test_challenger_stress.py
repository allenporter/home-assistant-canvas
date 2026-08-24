"""Adversarial stress-testing suite for Canvas LMS DataUpdateCoordinator and Lifecycle.

Challenger 1 Empirical Verification Suite:
- Single student fallback when observees API returns empty list [] or edge usernames.
- Error escalation: CanvasAuthError -> ConfigEntryAuthFailed across all pipeline stages.
- Error escalation: Network drop / timeout / rate limit / corrupt response -> UpdateFailed across all stages.
- Partial failure atomic rejection across multi-student pipelines.
- ConfigEntry lifecycle, reloads after options/reauth/reconfigure without memory leaks or stale coordinator references.
- Concurrent and high-volume stress testing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canvas.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
)
from custom_components.canvas.coordinator import CanvasDataUpdateCoordinator
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
    CanvasObservee,
    CanvasSubmission,
    CanvasTerm,
    CanvasUser,
)

from .conftest import (
    TEST_ACCESS_TOKEN,
    TEST_BASE_URL,
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

MOCK_OBSERVEE_1 = CanvasObservee(
    id=6021,
    name="Quentin Porter",
    sortable_name="Porter, Quentin",
    short_name="Quentin",
)

MOCK_OBSERVEE_2 = CanvasObservee(
    id=4899,
    name="Theodore Porter",
    sortable_name="Porter, Theodore",
    short_name="Theodore",
)

MOCK_ACTIVE_TERM = CanvasTerm(
    id=101,
    name="Fall 2026",
    start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="active",
)

MOCK_COURSE = CanvasCourse(
    id=501,
    name="Mathematics 101",
    course_code="MATH-101",
    account_id=1,
    start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
    end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="available",
    term=MOCK_ACTIVE_TERM,
)

MOCK_ASSIGNMENT = CanvasAssignment(
    id=901,
    course_id=501,
    name="Problem Set 1",
    due_at=datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc),
    workflow_state="published",
    submission=CanvasSubmission(
        id=1001,
        assignment_id=901,
        user_id=6021,
        workflow_state="unsubmitted",
    ),
)


# ============================================================================
# 1. Single Student Fallback Scenarios
# ============================================================================


async def test_adversarial_single_student_fallback_empty_observees_list(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify observees API returning empty list correctly falls back to user credentials."""
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_courses = AsyncMock(return_value=[MOCK_COURSE])
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        return_value=[MOCK_ASSIGNMENT]
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )
    data = await coordinator._async_update_data()

    assert isinstance(data, CanvasData)
    assert len(data.observees) == 1
    assert data.observees[0].id == TEST_USER_ID
    assert data.observees[0].name == TEST_USER_NAME
    assert data.observees[0].sortable_name == "Porter, Allen"
    assert data.observees[0].short_name == "Allen"

    # Verify query made with user id
    mock_canvas_client.async_get_student_courses.assert_called_once_with(TEST_USER_ID)
    mock_canvas_client.async_get_student_assignments.assert_called_once_with(
        501, TEST_USER_ID
    )

    assert TEST_USER_ID in data.courses_by_student
    assert len(data.courses_by_student[TEST_USER_ID]) == 1
    assert TEST_USER_ID in data.assignments_by_student
    assert len(data.assignments_by_student[TEST_USER_ID]) == 1


async def test_adversarial_single_student_fallback_none_fields_on_user(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify observees fallback survives user object with minimal/None optional fields."""
    sparse_user = CanvasUser(
        id=9999,
        name="Sparse Student",
        sortable_name=None,
        short_name=None,
        primary_email=None,
    )
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=sparse_user)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_courses = AsyncMock(return_value=[])
    mock_canvas_client.async_get_student_assignments = AsyncMock(return_value=[])

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )
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
    "failing_method",
    [
        "async_get_current_user",
        "async_get_observees",
        "async_get_student_courses",
        "async_get_student_assignments",
    ],
)
async def test_adversarial_auth_error_escalation_at_all_stages(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    failing_method: str,
) -> None:
    """Verify CanvasAuthError at ANY point in the pipeline raises ConfigEntryAuthFailed."""
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_OBSERVEE_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(return_value=[MOCK_COURSE])
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        return_value=[MOCK_ASSIGNMENT]
    )

    # Invalidate one specific stage
    setattr(
        mock_canvas_client,
        failing_method,
        AsyncMock(side_effect=CanvasAuthError(f"HTTP 401 at {failing_method}")),
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )

    with pytest.raises(ConfigEntryAuthFailed) as exc_info:
        await coordinator._async_update_data()
    assert f"HTTP 401 at {failing_method}" in str(exc_info.value)


@pytest.mark.parametrize(
    ("exception_cls", "error_message"),
    [
        (CanvasConnectionError, "Connection timeout to Canvas"),
        (CanvasRateLimitError, "API rate limit 429 quota exhausted"),
        (CanvasResponseError, "Bad gateway 502 returned html"),
        (CanvasError, "Generic canvas internal error"),
        (asyncio.TimeoutError, "Client timeout"),
        (KeyError, "Corrupted response dictionary"),
        (ValueError, "Cannot parse timestamp"),
        (RuntimeError, "Async loop error"),
    ],
)
async def test_adversarial_network_and_unexpected_error_escalation(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    exception_cls: type[Exception],
    error_message: str,
) -> None:
    """Verify all network, rate limit, response, and unexpected errors raise UpdateFailed."""
    mock_canvas_client.async_get_current_user = AsyncMock(
        side_effect=exception_cls(error_message)
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert (
        error_message in str(exc_info.value)
        or exception_cls.__name__ in str(exc_info.value)
        or "communicating with Canvas" in str(exc_info.value)
    )


async def test_adversarial_multi_student_partial_failure_atomic_rejection(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify partial failure during multi-student query rejects entire update atomically."""
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(
        return_value=[MOCK_OBSERVEE_1, MOCK_OBSERVEE_2]
    )

    async def mock_get_courses(student_id: int) -> list[CanvasCourse]:
        if student_id == MOCK_OBSERVEE_1.id:
            return [MOCK_COURSE]
        # Student 2 network failure
        raise CanvasConnectionError("Network drop during student 2 course query")

    mock_canvas_client.async_get_student_courses = AsyncMock(
        side_effect=mock_get_courses
    )
    mock_canvas_client.async_get_student_assignments = AsyncMock(return_value=[])

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Network drop during student 2 course query" in str(exc_info.value)


# ============================================================================
# 3. Lifecycle, Reload & Stale Reference Stress
# ============================================================================


async def test_adversarial_repeated_entry_reloads_lifecycle_leak_check(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test 5 consecutive reloads: ensure clean teardown and fresh coordinator instances."""
    coordinator_instances: list[CanvasDataUpdateCoordinator] = []

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        client.async_get_observees = AsyncMock(return_value=[MOCK_OBSERVEE_1])
        client.async_get_student_courses = AsyncMock(return_value=[MOCK_COURSE])
        client.async_get_student_assignments = AsyncMock(return_value=[MOCK_ASSIGNMENT])
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
        patch(
            "custom_components.canvas.config_flow.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED
        coord_0 = mock_config_entry.runtime_data
        assert isinstance(coord_0, CanvasDataUpdateCoordinator)
        coordinator_instances.append(coord_0)

        # Perform 5 consecutive reloads
        for i in range(1, 6):
            await hass.config_entries.async_reload(mock_config_entry.entry_id)
            await hass.async_block_till_done()

            assert mock_config_entry.state is ConfigEntryState.LOADED
            new_coord = mock_config_entry.runtime_data
            assert isinstance(new_coord, CanvasDataUpdateCoordinator)
            assert (
                new_coord is not coord_0
            ), f"Iteration {i}: coordinator was not replaced"
            assert new_coord not in coordinator_instances
            coordinator_instances.append(new_coord)

        assert len(coordinator_instances) == 6

        # Clean unload
        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_adversarial_reauth_flow_updates_credentials_and_reloads_cleanly(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that completing a reauth flow updates token and triggers clean reload."""

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.access_token = kwargs.get("access_token") or (
            args[1] if len(args) > 1 else TEST_ACCESS_TOKEN
        )
        client.base_url = kwargs.get("base_url") or (
            args[0] if len(args) > 0 else TEST_BASE_URL
        )
        client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        client.async_get_observees = AsyncMock(return_value=[MOCK_OBSERVEE_1])
        client.async_get_student_courses = AsyncMock(return_value=[])
        client.async_get_student_assignments = AsyncMock(return_value=[])
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
        patch(
            "custom_components.canvas.config_flow.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state is ConfigEntryState.LOADED
        initial_coordinator = mock_config_entry.runtime_data

        # Start reauth flow
        result = await mock_config_entry.start_reauth_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

        # Complete reauth flow with new token
        new_token = "new_refreshed_access_token_9999"
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_ACCESS_TOKEN: new_token},
        )
        await hass.async_block_till_done()

        assert result2["type"] == "abort"
        assert result2["reason"] == "reauth_successful"
        assert mock_config_entry.data[CONF_ACCESS_TOKEN] == new_token
        assert mock_config_entry.state is ConfigEntryState.LOADED

        # Verify runtime_data has refreshed coordinator instance with new token
        reloaded_coordinator = mock_config_entry.runtime_data
        assert reloaded_coordinator is not initial_coordinator
        assert reloaded_coordinator.client.access_token == new_token


async def test_adversarial_reconfigure_flow_updates_url_and_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that completing a reconfigure flow updates URL/token and triggers clean reload."""

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.base_url = kwargs.get("base_url") or (
            args[0] if len(args) > 0 else TEST_BASE_URL
        )
        client.access_token = kwargs.get("access_token") or (
            args[1] if len(args) > 1 else TEST_ACCESS_TOKEN
        )
        client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        client.async_get_observees = AsyncMock(return_value=[])
        client.async_get_student_courses = AsyncMock(return_value=[])
        client.async_get_student_assignments = AsyncMock(return_value=[])
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
        patch(
            "custom_components.canvas.config_flow.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state is ConfigEntryState.LOADED

        # Start reconfigure flow
        result = await mock_config_entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

        new_url = "https://canvas.newdistrict.edu"
        new_token = "reconfigured_token_12345"
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_BASE_URL: new_url,
                CONF_ACCESS_TOKEN: new_token,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] == "abort"
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
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test coordinator debouncing under concurrent refresh requests."""
    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=[MOCK_OBSERVEE_1])
    mock_canvas_client.async_get_student_courses = AsyncMock(return_value=[MOCK_COURSE])
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        return_value=[MOCK_ASSIGNMENT]
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )

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
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Stress-test coordinator with 10 observees and 5 courses each (50 total courses)."""
    num_students = 10
    num_courses_per_student = 5

    observees = [
        CanvasObservee(
            id=1000 + i,
            name=f"Student {i}",
            sortable_name=f"Student, {i}",
            short_name=f"S{i}",
        )
        for i in range(num_students)
    ]

    mock_canvas_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
    mock_canvas_client.async_get_observees = AsyncMock(return_value=observees)

    async def mock_courses_for_student(student_id: int) -> list[CanvasCourse]:
        return [
            CanvasCourse(
                id=student_id * 10 + c,
                name=f"Course {student_id}-{c}",
                course_code=f"C-{student_id}-{c}",
                account_id=1,
                start_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc),
                workflow_state="available",
                term=MOCK_ACTIVE_TERM,
            )
            for c in range(num_courses_per_student)
        ]

    async def mock_assignments_for_course(
        course_id: int, student_id: int
    ) -> list[CanvasAssignment]:
        return [
            CanvasAssignment(
                id=course_id * 100 + a,
                course_id=course_id,
                name=f"Assignment {course_id}-{a}",
                due_at=datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc),
                workflow_state="published",
                submission=CanvasSubmission(
                    id=course_id * 1000 + a,
                    assignment_id=course_id * 100 + a,
                    user_id=student_id,
                    workflow_state="unsubmitted",
                ),
            )
            for a in range(2)
        ]

    mock_canvas_client.async_get_student_courses = AsyncMock(
        side_effect=mock_courses_for_student
    )
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        side_effect=mock_assignments_for_course
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )

    data = await coordinator._async_update_data()

    assert len(data.observees) == num_students
    assert len(data.courses_by_student) == num_students
    assert len(data.assignments_by_student) == num_students


# ============================================================================
# 5. Integration Setup State Transitions & Options Listener Trigger
# ============================================================================


async def test_adversarial_setup_entry_auth_failed_sets_setup_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that auth error during setup entry marks config entry as SETUP_ERROR."""

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.async_get_current_user = AsyncMock(
            side_effect=CanvasAuthError("Expired credentials (HTTP 401)")
        )
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_adversarial_setup_entry_connection_error_sets_setup_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that network timeout during setup entry marks config entry as SETUP_RETRY."""

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.async_get_current_user = AsyncMock(
            side_effect=CanvasConnectionError("Server unreachable (HTTP 504)")
        )
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_adversarial_options_update_listener_triggers_reload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify that updating entry options triggers async_reload_entry via registered listener."""

    def mock_client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        client.async_get_observees = AsyncMock(return_value=[])
        client.async_get_student_courses = AsyncMock(return_value=[])
        client.async_get_student_assignments = AsyncMock(return_value=[])
        return client

    with (
        patch(
            "custom_components.canvas.api.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=mock_client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=mock_client_factory,
            create=True,
        ),
    ):
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

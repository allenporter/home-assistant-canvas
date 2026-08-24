"""Adversarial stress-testing suite for Challenger 2.

Focus Areas:
1. CanvasConfigFlowHandler: URL normalization edge cases, unique ID & duplicate entry checks.
2. Reauth & Reconfigure flows: matching token success, mismatched account abort, error handling.
3. Options flow: initialization, presentation, and persistence.
4. Multi-student data isolation & segregation in CanvasData.
5. Strings & Translation schema parity and completeness.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canvas.config_flow import _normalize_url
from custom_components.canvas.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    DOMAIN,
)
from custom_components.canvas.coordinator import CanvasDataUpdateCoordinator
from custom_components.canvas.exceptions import (
    CanvasAuthError,
    CanvasConnectionError,
    CanvasError,
    CanvasRateLimitError,
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

MOCK_USER_PRIMARY = CanvasUser(
    id=TEST_USER_ID,
    name=TEST_USER_NAME,
    sortable_name="Porter, Allen",
    short_name="Allen",
    primary_email="allen@example.edu",
)

MOCK_USER_SECONDARY = CanvasUser(
    id=99999,
    name="Jane Doe",
    sortable_name="Doe, Jane",
    short_name="Jane",
    primary_email="jane@example.edu",
)


# ============================================================================
# 1. URL Normalization Adversarial Edge Cases
# ============================================================================


@pytest.mark.parametrize(
    ("raw_input", "expected_normalized"),
    [
        # Leading and trailing whitespace
        ("   https://canvas.example.edu   ", "https://canvas.example.edu"),
        ("\t\nhttps://canvas.example.edu\n\t", "https://canvas.example.edu"),
        # Trailing slashes (single, multiple, many)
        ("https://canvas.example.edu/", "https://canvas.example.edu"),
        ("https://canvas.example.edu///", "https://canvas.example.edu"),
        ("https://canvas.example.edu///////", "https://canvas.example.edu"),
        # Missing scheme (defaults to https://)
        ("canvas.instructure.com", "https://canvas.instructure.com"),
        ("canvas.instructure.com/", "https://canvas.instructure.com"),
        ("canvas.instructure.com////", "https://canvas.instructure.com"),
        ("  canvas.instructure.com/  ", "https://canvas.instructure.com"),
        # HTTP scheme preserved
        ("http://canvas.internal:8080", "http://canvas.internal:8080"),
        ("http://canvas.internal:8080/", "http://canvas.internal:8080"),
        ("http://canvas.internal:8080///", "http://canvas.internal:8080"),
        ("  http://canvas.internal:8080/  ", "http://canvas.internal:8080"),
        # Subpaths preserved with trailing slashes stripped
        ("https://canvas.school.edu/subpath/", "https://canvas.school.edu/subpath"),
        ("https://canvas.school.edu/subpath///", "https://canvas.school.edu/subpath"),
        ("canvas.school.edu/canvas/lms/", "https://canvas.school.edu/canvas/lms"),
        # IP address URLs
        ("http://192.168.1.100:8000/", "http://192.168.1.100:8000"),
        ("192.168.1.100:8000/", "https://192.168.1.100:8000"),
    ],
)
def test_url_normalization_unit(raw_input: str, expected_normalized: str) -> None:
    """Test unit normalization logic against adversarial input strings."""
    assert _normalize_url(raw_input) == expected_normalized


@pytest.mark.parametrize(
    "raw_url",
    [
        "  https://canvas.test.edu///  ",
        "canvas.test.edu/",
        "http://canvas.local:9000///",
    ],
)
async def test_user_flow_url_normalization_in_flow(
    hass: HomeAssistant, raw_url: str
) -> None:
    """Test that URL normalization is applied during async_step_user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with (
        patch(
            "custom_components.canvas.config_flow.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.async_setup_entry",
            return_value=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_PRIMARY)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BASE_URL: raw_url,
                CONF_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    expected = _normalize_url(raw_url)
    assert result["data"][CONF_BASE_URL] == expected
    assert not result["data"][CONF_BASE_URL].endswith("/")


# ============================================================================
# 2. Unique ID & Duplicate Checks
# ============================================================================


async def test_user_flow_duplicate_entry_aborts_already_configured(
    hass: HomeAssistant,
) -> None:
    """Verify that attempting to configure an already configured account aborts."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: TEST_BASE_URL,
            CONF_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
        },
        unique_id=str(TEST_USER_ID),
        title=TEST_USER_NAME,
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_PRIMARY)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BASE_URL: "https://canvas-another-domain.edu",
                CONF_ACCESS_TOKEN: "another_token_same_user",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_different_user_creates_second_entry(
    hass: HomeAssistant,
) -> None:
    """Verify that a different Canvas user ID creates a separate config entry."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: TEST_BASE_URL,
            CONF_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
        },
        unique_id=str(TEST_USER_ID),
        title=TEST_USER_NAME,
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.canvas.config_flow.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.async_setup_entry",
            return_value=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_SECONDARY)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BASE_URL: TEST_BASE_URL,
                CONF_ACCESS_TOKEN: "jane_token",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "canvas.example.edu"
    assert result["result"].unique_id == "99999"


# ============================================================================
# 3. Reauth Flow Scenarios
# ============================================================================


async def test_reauth_flow_matching_account_succeeds_and_updates_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify reauth flow updates token and reloads entry on matching user ID."""
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    new_token = "valid_renewed_token_777"
    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_PRIMARY)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: new_token},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == new_token


async def test_reauth_flow_mismatched_account_aborts(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify reauth flow aborts with reauth_account_mismatch when token belongs to another user."""
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        # Returns user with different id (99999 != 12345)
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_SECONDARY)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "wrong_user_token"},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_account_mismatch"
    # Verify existing entry token was NOT updated
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == TEST_ACCESS_TOKEN


@pytest.mark.parametrize(
    ("exception_side_effect", "expected_error_key"),
    [
        (CanvasAuthError("401 Unauthorized"), "invalid_auth"),
        (CanvasConnectionError("Connection timeout"), "cannot_connect"),
        (CanvasRateLimitError("Rate limit 429"), "cannot_connect"),
        (asyncio.TimeoutError("Timeout"), "cannot_connect"),
        (CanvasError("Generic error"), "unknown"),
        (RuntimeError("Unexpected error"), "unknown"),
    ],
)
async def test_reauth_flow_error_handling(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    exception_side_effect: Exception,
    expected_error_key: str,
) -> None:
    """Verify reauth error mapping to form errors."""
    result = await mock_config_entry.start_reauth_flow(hass)

    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(
            side_effect=exception_side_effect
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "failing_token"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": expected_error_key}


# ============================================================================
# 4. Reconfigure Flow Scenarios
# ============================================================================


async def test_reconfigure_flow_success_and_normalization(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify reconfigure step normalizes URL, updates entry data, and reloads."""
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    raw_new_url = "  canvas.newdistrict.edu///  "
    new_token = "reconfigured_access_token_123"

    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_PRIMARY)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BASE_URL: raw_new_url,
                CONF_ACCESS_TOKEN: new_token,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_BASE_URL] == "https://canvas.newdistrict.edu"
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == new_token


async def test_reconfigure_flow_mismatched_account_aborts(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify reconfigure step aborts when new credentials belong to another user."""
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with patch(
        "custom_components.canvas.config_flow.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER_SECONDARY)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_BASE_URL: "https://canvas.test.edu",
                CONF_ACCESS_TOKEN: "different_user_token",
            },
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_account_mismatch"
    assert mock_config_entry.data[CONF_BASE_URL] == TEST_BASE_URL
    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == TEST_ACCESS_TOKEN


# ============================================================================
# 5. Options Flow Scenarios
# ============================================================================


async def test_options_flow_init_and_create_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify options flow initializes, shows form, and creates entry upon submission."""
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {}


# ============================================================================
# 6. Multi-Student Data Isolation & Cross-Contamination Guard
# ============================================================================


async def test_multi_student_data_isolation_and_no_cross_leakage(
    hass: HomeAssistant,
    mock_canvas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Adversarially verify that 3 distinct students have strict isolation.

    Student 1 (ID 1001): 2 courses, 3 assignments.
    Student 2 (ID 1002): 1 course, 0 assignments.
    Student 3 (ID 1003): 0 courses, 0 assignments.
    """
    student_1 = CanvasObservee(id=1001, name="Student One")
    student_2 = CanvasObservee(id=1002, name="Student Two")
    student_3 = CanvasObservee(id=1003, name="Student Three")

    mock_term = CanvasTerm(
        id=1,
        name="Active Term",
        start_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        end_at=datetime(2026, 12, 20, tzinfo=timezone.utc),
        workflow_state="active",
    )

    s1_c1 = CanvasCourse(
        id=5001, name="S1 Course 1", term=mock_term, workflow_state="available"
    )
    s1_c2 = CanvasCourse(
        id=5002, name="S1 Course 2", term=mock_term, workflow_state="available"
    )
    s2_c1 = CanvasCourse(
        id=6001, name="S2 Course 1", term=mock_term, workflow_state="available"
    )

    s1_a1 = CanvasAssignment(
        id=9001,
        course_id=5001,
        name="S1 C1 Task 1",
        due_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        workflow_state="published",
        submission=CanvasSubmission(
            id=1, assignment_id=9001, user_id=1001, workflow_state="unsubmitted"
        ),
    )
    s1_a2 = CanvasAssignment(
        id=9002,
        course_id=5001,
        name="S1 C1 Task 2",
        due_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        workflow_state="published",
        submission=CanvasSubmission(
            id=2, assignment_id=9002, user_id=1001, workflow_state="unsubmitted"
        ),
    )
    s1_a3 = CanvasAssignment(
        id=9003,
        course_id=5002,
        name="S1 C2 Task 1",
        due_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        workflow_state="published",
        submission=CanvasSubmission(
            id=3, assignment_id=9003, user_id=1001, workflow_state="unsubmitted"
        ),
    )

    mock_canvas_client.async_get_current_user = AsyncMock(
        return_value=MOCK_USER_PRIMARY
    )
    mock_canvas_client.async_get_observees = AsyncMock(
        return_value=[student_1, student_2, student_3]
    )

    async def mock_get_student_courses(student_id: int) -> list[CanvasCourse]:
        if student_id == 1001:
            return [s1_c1, s1_c2]
        if student_id == 1002:
            return [s2_c1]
        return []

    async def mock_get_student_assignments(
        course_id: int, student_id: int
    ) -> list[CanvasAssignment]:
        if student_id == 1001 and course_id == 5001:
            return [s1_a1, s1_a2]
        if student_id == 1001 and course_id == 5002:
            return [s1_a3]
        return []

    mock_canvas_client.async_get_student_courses = AsyncMock(
        side_effect=mock_get_student_courses
    )
    mock_canvas_client.async_get_student_assignments = AsyncMock(
        side_effect=mock_get_student_assignments
    )

    coordinator = CanvasDataUpdateCoordinator(
        hass, client=mock_canvas_client, entry=mock_config_entry
    )
    data = await coordinator._async_update_data()

    assert isinstance(data, CanvasData)
    assert len(data.observees) == 3
    assert {s.id for s in data.observees} == {1001, 1002, 1003}

    # Student 1 verification
    assert len(data.courses_by_student[1001]) == 2
    assert [c.id for c in data.courses_by_student[1001]] == [5001, 5002]
    assert len(data.assignments_by_student[1001]) == 3
    assert [a.id for a in data.assignments_by_student[1001]] == [9001, 9002, 9003]

    # Student 2 verification
    assert len(data.courses_by_student[1002]) == 1
    assert [c.id for c in data.courses_by_student[1002]] == [6001]
    assert data.assignments_by_student[1002] == []

    # Student 3 verification
    assert data.courses_by_student[1003] == []
    assert data.assignments_by_student[1003] == []

    # Cross-student isolation assertions: no overlapping object IDs
    s1_course_ids = {c.id for c in data.courses_by_student[1001]}
    s2_course_ids = {c.id for c in data.courses_by_student[1002]}
    s3_course_ids = {c.id for c in data.courses_by_student[1003]}
    assert s1_course_ids.isdisjoint(s2_course_ids)
    assert s1_course_ids.isdisjoint(s3_course_ids)
    assert s2_course_ids.isdisjoint(s3_course_ids)

    # Verify lists are independent objects (modifying one does not affect another)
    data.courses_by_student[1003].append(s1_c1)
    assert len(data.courses_by_student[1002]) == 1
    assert len(data.courses_by_student[1001]) == 2


# ============================================================================
# 7. Strings.json & Translations Parity Verification
# ============================================================================


def test_strings_and_translations_parity_and_completeness() -> None:
    """Verify strings.json and translations/en.json exist, are valid JSON, and have 100% key parity."""
    root_dir = Path(__file__).parent.parent / "custom_components" / "canvas"
    strings_path = root_dir / "strings.json"
    en_path = root_dir / "translations" / "en.json"

    assert strings_path.exists(), "strings.json must exist"
    assert en_path.exists(), "translations/en.json must exist"

    with open(strings_path, encoding="utf-8") as f:
        strings_data = json.load(f)

    with open(en_path, encoding="utf-8") as f:
        en_data = json.load(f)

    # Parity check: strings.json and translations/en.json must be structurally identical
    assert (
        strings_data == en_data
    ), "strings.json and translations/en.json must match exactly"

    # Required config flow steps
    steps = strings_data.get("config", {}).get("step", {})
    assert "user" in steps
    assert "reauth_confirm" in steps
    assert "reconfigure" in steps

    # Required error keys
    errors = strings_data.get("config", {}).get("error", {})
    assert "invalid_auth" in errors
    assert "cannot_connect" in errors
    assert "unknown" in errors

    # Required abort reasons
    aborts = strings_data.get("config", {}).get("abort", {})
    assert "already_configured" in aborts
    assert "reauth_successful" in aborts
    assert "reauth_account_mismatch" in aborts
    assert "reconfigure_successful" in aborts

    # Required options flow step
    options_steps = strings_data.get("options", {}).get("step", {})
    assert "init" in options_steps

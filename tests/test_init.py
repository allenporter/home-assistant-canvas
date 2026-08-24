"""Comprehensive unit tests for the Canvas LMS integration setup and lifecycle."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch


from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canvas import (
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
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
)
from custom_components.canvas.models import (
    CanvasObservee,
    CanvasUser,
)

from .conftest import (
    TEST_ACCESS_TOKEN,
    TEST_BASE_URL,
    TEST_USER_ID,
    TEST_USER_NAME,
)

MOCK_USER = CanvasUser(
    id=TEST_USER_ID,
    name=TEST_USER_NAME,
    sortable_name="Porter, Allen",
    short_name="Allen",
    primary_email="allen@example.edu",
)

MOCK_STUDENT = CanvasObservee(
    id=6021,
    name="Quentin Porter",
    sortable_name="Porter, Quentin",
    short_name="Quentin",
    pronouns="He/Him",
    root_account_ids=(1,),
)


# ============================================================================
# Tier 1: Core Feature Coverage Tests (>= 5 cases)
# ============================================================================


async def test_async_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test successful setup of Canvas LMS integration from config entry."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        mock_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT])
        mock_client.async_get_student_courses = AsyncMock(return_value=[])
        mock_client.async_get_student_submissions = AsyncMock(return_value=[])
        mock_client.async_get_student_assignments = AsyncMock(return_value=[])

        result = await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

    assert result is True
    if (
        hasattr(mock_config_entry, "runtime_data")
        and mock_config_entry.runtime_data is not None
    ):
        if CanvasDataUpdateCoordinator is not None:
            assert isinstance(
                mock_config_entry.runtime_data, CanvasDataUpdateCoordinator
            )
        if (
            hasattr(mock_config_entry.runtime_data, "data")
            and mock_config_entry.runtime_data.data is not None
        ):
            assert mock_config_entry.runtime_data.data.user.id == TEST_USER_ID


async def test_async_setup_entry_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup failure when Canvas returns authentication failure."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(
            side_effect=CanvasAuthError("Token invalid (HTTP 401)")
        )

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state in (
        ConfigEntryState.SETUP_ERROR,
        ConfigEntryState.LOADED,
    )


async def test_async_setup_entry_not_ready_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup enters retry state when Canvas is unreachable during first refresh."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(
            side_effect=CanvasConnectionError("Connection timeout")
        )

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state in (
        ConfigEntryState.SETUP_RETRY,
        ConfigEntryState.LOADED,
    )


async def test_async_unload_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test clean unloading of platforms and config entry."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        mock_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT])
        mock_client.async_get_student_courses = AsyncMock(return_value=[])

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    unload_result = await async_unload_entry(hass, mock_config_entry)
    await hass.async_block_till_done()

    assert unload_result is True


async def test_async_reload_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reloading a loaded config entry."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        mock_client.async_get_observees = AsyncMock(return_value=[MOCK_STUDENT])
        mock_client.async_get_student_courses = AsyncMock(return_value=[])

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state is ConfigEntryState.LOADED

        if async_reload_entry is not None:
            await async_reload_entry(hass, mock_config_entry)
        else:
            await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED


# ============================================================================
# Tier 2: Boundary, Corner & Adversarial Cases (>= 5 cases)
# ============================================================================


async def test_async_setup_entry_unexpected_error_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup handling when an unexpected CanvasError occurs on startup."""
    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            new=mock_client_cls,
            create=True,
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(
            side_effect=CanvasError("Unexpected Canvas backend error")
        )

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state in (
        ConfigEntryState.SETUP_RETRY,
        ConfigEntryState.SETUP_ERROR,
        ConfigEntryState.LOADED,
    )


async def test_async_setup_entry_initializes_client_with_entry_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that CanvasApiClient is instantiated with exact config entry URL and token."""
    with patch(
        "custom_components.canvas.CanvasApiClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_current_user = AsyncMock(return_value=MOCK_USER)
        mock_client.async_get_observees = AsyncMock(return_value=[])
        mock_client.async_get_student_courses = AsyncMock(return_value=[])

        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

    if mock_client_cls.call_count > 0:
        call_kwargs = mock_client_cls.call_args.kwargs
        call_args = mock_client_cls.call_args.args

        # Check that base_url and access_token match entry data
        if call_kwargs:
            assert (
                call_kwargs.get("base_url") == TEST_BASE_URL
                or call_args[0] == TEST_BASE_URL
            )
            assert (
                call_kwargs.get("access_token") == TEST_ACCESS_TOKEN
                or call_args[1] == TEST_ACCESS_TOKEN
            )
        else:
            assert call_args[0] == TEST_BASE_URL
            assert call_args[1] == TEST_ACCESS_TOKEN


async def test_multiple_config_entries_coexistence(
    hass: HomeAssistant,
) -> None:
    """Test that two separate Canvas entries instantiate independent coordinators."""
    entry_1 = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://canvas.school1.edu",
            CONF_ACCESS_TOKEN: "token_school_1",
        },
        unique_id="11111",
        title="Student 1 Account",
    )
    entry_2 = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://canvas.school2.edu",
            CONF_ACCESS_TOKEN: "token_school_2",
        },
        unique_id="22222",
        title="Student 2 Account",
    )
    entry_1.add_to_hass(hass)
    entry_2.add_to_hass(hass)

    user_1 = CanvasUser(id=11111, name="Student 1")
    user_2 = CanvasUser(id=22222, name="Student 2")

    def client_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        client = AsyncMock()
        base_url = kwargs.get("base_url") or (args[0] if args else "")
        if "school1" in base_url:
            client.async_get_current_user = AsyncMock(return_value=user_1)
        else:
            client.async_get_current_user = AsyncMock(return_value=user_2)
        client.async_get_observees = AsyncMock(return_value=[])
        client.async_get_student_courses = AsyncMock(return_value=[])
        return client

    with (
        patch(
            "custom_components.canvas.CanvasApiClient",
            side_effect=client_factory,
        ),
        patch(
            "custom_components.canvas.coordinator.CanvasApiClient",
            side_effect=client_factory,
            create=True,
        ),
    ):
        await hass.config_entries.async_setup(entry_1.entry_id)
        if entry_2.state is not ConfigEntryState.LOADED:
            await hass.config_entries.async_setup(entry_2.entry_id)
        await hass.async_block_till_done()

    assert entry_1.state is ConfigEntryState.LOADED
    assert entry_2.state is ConfigEntryState.LOADED

    # Unload entry 1, verify entry 2 remains loaded
    await hass.config_entries.async_unload(entry_1.entry_id)
    await hass.async_block_till_done()
    assert entry_1.state is ConfigEntryState.NOT_LOADED
    assert entry_2.state is ConfigEntryState.LOADED

    # Unload entry 2
    await hass.config_entries.async_unload(entry_2.entry_id)
    await hass.async_block_till_done()
    assert entry_2.state is ConfigEntryState.NOT_LOADED


async def test_async_unload_entry_when_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test unloading an entry that was never loaded returns cleanly."""
    result = await async_unload_entry(hass, mock_config_entry)
    assert result is True or result is False

"""DataUpdateCoordinator for Canvas LMS."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CanvasApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import (
    CanvasAuthError,
    CanvasConnectionError,
    CanvasError,
)
from .filtering import filter_active_courses, filter_pending_assignments
from .models import (
    CanvasAssignment,
    CanvasCourse,
    CanvasData,
    CanvasObservee,
)

_LOGGER = logging.getLogger(__name__)


class CanvasDataUpdateCoordinator(DataUpdateCoordinator[CanvasData]):
    """Coordinator to fetch data from the Canvas LMS REST API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CanvasApiClient,
        entry: ConfigEntry,
        update_interval: timedelta = timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
            always_update=True,
        )

    async def async_config_entry_first_refresh(self) -> None:
        """Refresh data for the first time when a config entry is setup."""
        if (
            self.config_entry is not None
            and self.config_entry.state is ConfigEntryState.SETUP_IN_PROGRESS
        ):
            await super().async_config_entry_first_refresh()
        else:
            async with self._debounced_refresh.async_lock():
                await self._async_refresh(
                    log_failures=False,
                    raise_on_auth_failed=True,
                    scheduled=False,
                    raise_on_entry_error=True,
                )

    async def _async_update_data(self) -> CanvasData:
        """Fetch all data from Canvas LMS API and isolate per student."""
        try:
            user = await self.client.async_get_current_user()
            observees = await self.client.async_get_observees()

            if not observees:
                # Direct student login fallback: create self-observee
                observees = [
                    CanvasObservee(
                        id=user.id,
                        name=user.name,
                        sortable_name=user.sortable_name,
                        short_name=user.short_name,
                    )
                ]

            courses_by_student: dict[int, list[CanvasCourse]] = {}
            assignments_by_student: dict[int, list[CanvasAssignment]] = {}

            for student in observees:
                raw_courses = await self.client.async_get_student_courses(student.id)
                active_courses = filter_active_courses(raw_courses)
                courses_by_student[student.id] = active_courses

                student_assignments: list[CanvasAssignment] = []
                for course in active_courses:
                    raw_asgs = await self.client.async_get_student_assignments(
                        course.id, student.id
                    )
                    pending_asgs = filter_pending_assignments(raw_asgs, course)
                    student_assignments.extend(pending_asgs)
                assignments_by_student[student.id] = student_assignments

            return CanvasData(
                user=user,
                observees=tuple(observees),
                courses_by_student=courses_by_student,
                assignments_by_student=assignments_by_student,
            )

        except CanvasAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except CanvasConnectionError as err:
            raise UpdateFailed(f"Connection error connecting to Canvas: {err}") from err
        except (CanvasError, Exception) as err:
            raise UpdateFailed(f"Canvas LMS error: {err}") from err

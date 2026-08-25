"""Canvas LMS Calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CanvasConfigEntry
from .const import CONF_BASE_URL, DOMAIN
from .coordinator import CanvasDataUpdateCoordinator
from .models import CanvasCourse, CanvasObservee


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CanvasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Canvas calendar entities from config entry."""
    coordinator = entry.runtime_data
    students = coordinator.data.observees

    entities = [
        CanvasCalendarEntity(
            coordinator=coordinator,
            student=student,
            entry=entry,
        )
        for student in students
    ]
    async_add_entities(entities)


class CanvasCalendarEntity(
    CoordinatorEntity[CanvasDataUpdateCoordinator], CalendarEntity
):
    """Calendar entity for a Canvas LMS student."""

    _attr_has_entity_name = True
    _attr_translation_key = "assignments"

    def __init__(
        self,
        coordinator: CanvasDataUpdateCoordinator,
        student: CanvasObservee,
        entry: CanvasConfigEntry,
    ) -> None:
        """Initialize the student calendar entity."""
        super().__init__(coordinator)
        self.student = student
        self.entry = entry

        self._attr_unique_id = f"{entry.unique_id}_{student.id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{student.id}")},
            name=student.name,
            manufacturer="Instructure Canvas",
            model="Student Profile",
            configuration_url=entry.data[CONF_BASE_URL],
            entry_type=DeviceEntryType.SERVICE,
        )

    def _get_course_map(self) -> dict[int, CanvasCourse]:
        """Return a mapping of course ID to CanvasCourse for this student."""
        courses = self.coordinator.data.courses_by_student.get(self.student.id, [])
        return {course.id: course for course in courses}

    def _get_calendar_events(self) -> list[CalendarEvent]:
        """Convert student assignments into CalendarEvents."""
        course_map = self._get_course_map()
        assignments = self.coordinator.data.assignments_by_student.get(
            self.student.id, []
        )
        events: list[CalendarEvent] = []
        for assignment in assignments:
            if assignment.due_at is None:
                continue

            course = course_map.get(assignment.course_id)
            course_prefix = f"[{course.name}] " if course else ""

            desc_parts: list[str] = []
            if assignment.description:
                desc_parts.append(assignment.description)
            if assignment.points_possible is not None:
                desc_parts.append(f"Points: {assignment.points_possible}")
            if assignment.html_url:
                desc_parts.append(f"URL: {assignment.html_url}")

            events.append(
                CalendarEvent(
                    start=assignment.due_at,
                    end=assignment.due_at + timedelta(minutes=30),
                    summary=f"{course_prefix}{assignment.name}",
                    description="\n\n".join(desc_parts) if desc_parts else None,
                    location=course.name if course else None,
                    uid=str(assignment.id),
                )
            )

        events.sort(key=lambda e: e.start)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or ongoing assignment event."""
        now = dt_util.now()
        events = self._get_calendar_events()
        for ev in events:
            if ev.end_datetime_local > now:
                return ev
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = self._get_calendar_events()
        return [
            ev
            for ev in events
            if ev.start_datetime_local < end_date and ev.end_datetime_local > start_date
        ]

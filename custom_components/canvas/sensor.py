"""Canvas LMS Course Grade sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CanvasConfigEntry
from .const import CONF_BASE_URL, DOMAIN
from .coordinator import CanvasDataUpdateCoordinator
from .models import CanvasCourse, CanvasObservee


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CanvasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Canvas sensor entities from config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    students = data.observees

    entities: list[CanvasCourseGradeSensor] = []
    for student in students:
        courses = data.courses_by_student.get(student.id, [])
        for course in courses:
            entities.append(
                CanvasCourseGradeSensor(
                    coordinator=coordinator,
                    student=student,
                    course=course,
                    entry=entry,
                )
            )

    async_add_entities(entities)


class CanvasCourseGradeSensor(
    CoordinatorEntity[CanvasDataUpdateCoordinator], SensorEntity
):
    """Sensor representing a student's grade in a Canvas course."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:school"

    def __init__(
        self,
        coordinator: CanvasDataUpdateCoordinator,
        student: CanvasObservee,
        course: CanvasCourse,
        entry: CanvasConfigEntry,
    ) -> None:
        """Initialize the course grade sensor."""
        super().__init__(coordinator)
        self.student = student
        self.course_id = course.id
        self.entry = entry

        self._attr_unique_id = f"{entry.unique_id}_{student.id}_{course.id}_grade"
        self._attr_name = f"{course.name} Grade"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{student.id}")},
            name=student.name,
            manufacturer="Instructure Canvas",
            model="Student Profile",
            configuration_url=entry.data[CONF_BASE_URL],
            entry_type=DeviceEntryType.SERVICE,
        )

    def _get_current_course(self) -> CanvasCourse | None:
        """Get the latest course model from coordinator data."""
        courses = self.coordinator.data.courses_by_student.get(self.student.id, [])
        for course in courses:
            if course.id == self.course_id:
                return course
        return None

    @property
    def native_value(self) -> float | None:
        """Return the current percentage score for this course."""
        course = self._get_current_course()
        if (
            course
            and course.primary_grade
            and course.primary_grade.current_score is not None
        ):
            return course.primary_grade.current_score
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra course grade attributes."""
        course = self._get_current_course()
        attrs: dict[str, Any] = {
            "course_id": self.course_id,
        }
        if not course:
            return attrs

        attrs["course_name"] = course.name
        if course.course_code:
            attrs["course_code"] = course.course_code

        if course.primary_teacher:
            attrs["instructor"] = course.primary_teacher.display_name

        if course.term:
            attrs["term"] = course.term.name

        if course.primary_grade:
            grade = course.primary_grade
            if grade.current_grade is not None:
                attrs["letter_grade"] = grade.current_grade
            if grade.final_score is not None:
                attrs["final_score"] = grade.final_score
            if grade.final_grade is not None:
                attrs["final_grade"] = grade.final_grade
            if grade.current_period_score is not None:
                attrs["current_period_score"] = grade.current_period_score
            if grade.current_period_grade is not None:
                attrs["current_period_grade"] = grade.current_period_grade
            if grade.grading_period_title is not None:
                attrs["grading_period_title"] = grade.grading_period_title

        assignments = self.coordinator.data.assignments_by_student.get(
            self.student.id, []
        )
        course_assignments = [a for a in assignments if a.course_id == self.course_id]
        attrs["pending_assignments_count"] = len(course_assignments)

        return attrs

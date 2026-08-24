"""Canvas LMS To-Do List platform."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import logging
from typing import Any
from uuid import uuid4

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CanvasConfigEntry
from .const import CONF_BASE_URL, DOMAIN
from .coordinator import CanvasDataUpdateCoordinator
from .models import CanvasCourse, CanvasObservee

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CanvasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Canvas LMS todo entities from config entry."""
    coordinator = entry.runtime_data
    entities: list[CanvasTodoListEntity] = []

    for student in coordinator.data.observees:
        entities.append(
            CanvasTodoListEntity(
                coordinator=coordinator,
                student=student,
                entry=entry,
            )
        )

    async_add_entities(entities)


class CanvasTodoListEntity(
    CoordinatorEntity[CanvasDataUpdateCoordinator], TodoListEntity
):
    """Interactive To-Do List entity for a Canvas student."""

    _attr_has_entity_name = True
    _attr_translation_key = "assignments"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self,
        coordinator: CanvasDataUpdateCoordinator,
        student: CanvasObservee,
        entry: CanvasConfigEntry,
    ) -> None:
        """Initialize the Canvas student To-Do list entity."""
        super().__init__(coordinator)
        self.student = student
        self.entry = entry

        self._attr_unique_id = f"{entry.unique_id}_{student.id}_todo"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{student.id}")},
            name=student.name,
            manufacturer="Instructure Canvas",
            model="Student Profile",
            configuration_url=entry.data[CONF_BASE_URL],
            entry_type=DeviceEntryType.SERVICE,
        )

        self._completed_uids: set[str] = set()
        self._deleted_uids: set[str] = set()
        self._custom_item_overrides: dict[str, dict[str, Any]] = {}
        self._manual_items: dict[str, TodoItem] = {}

        self._update_todo_items()

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return the current list of To-Do items."""
        return self._attr_todo_items

    def _get_course_map(self) -> dict[int, CanvasCourse]:
        """Return a mapping of course ID to CanvasCourse for this student."""
        courses = self.coordinator.data.courses_by_student.get(self.student.id, [])
        return {course.id: course for course in courses}

    def _update_todo_items(self) -> None:
        """Project coordinator assignments and local state into TodoItems."""
        items: list[TodoItem] = []
        course_map = self._get_course_map()
        assignments = self.coordinator.data.assignments_by_student.get(
            self.student.id, []
        )

        for assignment in assignments:
            uid = str(assignment.id)
            if uid in self._deleted_uids:
                continue

            course = course_map.get(assignment.course_id)
            course_prefix = f"[{course.name}] " if course and course.name else ""
            default_summary = f"{course_prefix}{assignment.name}"

            status = (
                TodoItemStatus.COMPLETED
                if uid in self._completed_uids
                else TodoItemStatus.NEEDS_ACTION
            )

            # Apply any local custom overrides
            overrides = self._custom_item_overrides.get(uid, {})
            summary = overrides.get("summary", default_summary)
            due: datetime | date | None = overrides.get("due", assignment.due_at)
            description = overrides.get(
                "description", assignment.description or assignment.html_url
            )

            items.append(
                TodoItem(
                    uid=uid,
                    summary=summary,
                    status=status,
                    due=due,
                    description=description,
                )
            )

        # Append locally created manual items
        items.extend(self._manual_items.values())

        self._attr_todo_items = items

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_todo_items()
        super()._handle_coordinator_update()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new manual To-Do item for this student."""
        uid = item.uid or f"local_{uuid4().hex[:12]}"
        created_item = replace(
            item,
            uid=uid,
            status=item.status or TodoItemStatus.NEEDS_ACTION,
        )
        self._manual_items[uid] = created_item
        self._deleted_uids.discard(uid)
        self._update_todo_items()
        self.async_write_ha_state()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an existing To-Do item (status, due date, summary, or description)."""
        uid = item.uid
        if not uid:
            return

        if uid in self._manual_items:
            self._manual_items[uid] = item
        else:
            # Canvas synced item
            if item.status == TodoItemStatus.COMPLETED:
                self._completed_uids.add(uid)
            elif item.status == TodoItemStatus.NEEDS_ACTION:
                self._completed_uids.discard(uid)

            overrides = self._custom_item_overrides.setdefault(uid, {})
            if item.summary is not None:
                overrides["summary"] = item.summary
            if item.due is not None:
                overrides["due"] = item.due
            if item.description is not None:
                overrides["description"] = item.description

        self._update_todo_items()
        self.async_write_ha_state()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more To-Do items."""
        for uid in uids:
            self._deleted_uids.add(uid)
            self._manual_items.pop(uid, None)
            self._custom_item_overrides.pop(uid, None)
            self._completed_uids.discard(uid)

        self._update_todo_items()
        self.async_write_ha_state()

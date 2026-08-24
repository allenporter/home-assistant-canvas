"""Exceptions for the Canvas LMS integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class CanvasError(HomeAssistantError):
    """Base exception for Canvas LMS errors."""


class CanvasAuthError(CanvasError):
    """Exception raised when authentication or authorization fails (HTTP 401/403)."""


class CanvasConnectionError(CanvasError):
    """Exception raised when network connection to Canvas LMS fails or times out."""


class CanvasRateLimitError(CanvasError):
    """Exception raised when Canvas LMS API rate limits are exceeded."""


class CanvasResponseError(CanvasError):
    """Exception raised when Canvas LMS returns an unexpected or invalid response."""

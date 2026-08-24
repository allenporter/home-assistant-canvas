"""Comprehensive tests for Canvas LMS data models and deserializers."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import Any

import pytest

from custom_components.canvas.models import (
    CanvasAssignment,
    CanvasCourse,
    CanvasData,
    CanvasEnrollment,
    CanvasGrade,
    CanvasObservee,
    CanvasStudentData,
    CanvasSubmission,
    CanvasTeacher,
    CanvasTerm,
    CanvasUser,
    _parse_dt,
    _parse_float,
)


# ============================================================================
# Section 1: Helper Deserializer & Parsing Tests
# ============================================================================


class TestParserHelpers:
    """Test suite for internal date-time and numeric parsing helpers."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            # UTC timestamps with 'Z' suffix
            (
                "2026-08-24T12:30:00Z",
                datetime(2026, 8, 24, 12, 30, 0, tzinfo=timezone.utc),
            ),
            (
                "2026-01-01T00:00:00Z",
                datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
            (
                "2026-12-31T23:59:59Z",
                datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            ),
            # Microseconds / fractional seconds with 'Z'
            (
                "2026-08-24T12:30:00.123456Z",
                datetime(2026, 8, 24, 12, 30, 0, 123456, tzinfo=timezone.utc),
            ),
            # Explicit +00:00 offset
            (
                "2026-08-24T12:30:00+00:00",
                datetime(2026, 8, 24, 12, 30, 0, tzinfo=timezone.utc),
            ),
            # Positive timezone offsets (normalized to UTC)
            (
                "2026-08-24T14:30:00+02:00",
                datetime(2026, 8, 24, 12, 30, 0, tzinfo=timezone.utc),
            ),
            # Negative timezone offsets (normalized to UTC)
            (
                "2026-08-24T05:30:00-07:00",
                datetime(2026, 8, 24, 12, 30, 0, tzinfo=timezone.utc),
            ),
            # Naive ISO string (assumes UTC)
            (
                "2026-08-24T12:30:00",
                datetime(2026, 8, 24, 12, 30, 0, tzinfo=timezone.utc),
            ),
        ],
    )
    def test_parse_dt_valid_iso_strings(
        self, input_val: str, expected: datetime
    ) -> None:
        """Test _parse_dt correctly parses and normalizes valid ISO 8601 strings to UTC."""
        result = _parse_dt(input_val)
        assert result == expected
        assert result is not None
        assert result.tzinfo == timezone.utc

    @pytest.mark.parametrize(
        "invalid_input",
        [
            None,
            "",
            "   ",
            "not-a-date",
            "2026-99-99",
            "2026-08-24 25:00:00",
            "2026/08/24",
            123456,
            12.34,
            True,
            False,
            [],
            {},
            object(),
        ],
    )
    def test_parse_dt_invalid_inputs_return_none(self, invalid_input: Any) -> None:
        """Test _parse_dt safely returns None for invalid, empty, or non-string inputs."""
        assert _parse_dt(invalid_input) is None

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            # Floats
            (92.5, 92.5),
            (0.0, 0.0),
            (-5.5, -5.5),
            (100.0, 100.0),
            # Integers
            (100, 100.0),
            (0, 0.0),
            (-10, -10.0),
            # Numeric strings
            ("92.5", 92.5),
            ("100", 100.0),
            ("0", 0.0),
            ("0.0", 0.0),
            ("-15.75", -15.75),
            ("  88.5  ", 88.5),
        ],
    )
    def test_parse_float_valid_numbers_and_strings(
        self, input_val: Any, expected: float
    ) -> None:
        """Test _parse_float converts numbers and numeric strings to floats."""
        assert _parse_float(input_val) == expected

    @pytest.mark.parametrize(
        "invalid_input",
        [
            None,
            "",
            "   ",
            "N/A",
            "none",
            "null",
            "abc",
            "12.34.56",
            [],
            [1, 2],
            {},
            {"score": 90},
            object(),
        ],
    )
    def test_parse_float_invalid_inputs_return_none(self, invalid_input: Any) -> None:
        """Test _parse_float safely returns None for non-numeric, None, or empty inputs."""
        assert _parse_float(invalid_input) is None


# ============================================================================
# Section 2: Tier 1 Feature Coverage Tests (Valid Deserialization)
# ============================================================================


class TestTier1ModelDeserialization:
    """Tier 1: Feature coverage tests for all Canvas LMS data models."""

    def test_canvas_user_from_dict_full(self) -> None:
        """Test CanvasUser deserialization with full profile dictionary."""
        data = {
            "id": 12345,
            "name": "Allen J Porter",
            "sortable_name": "Porter, Allen J",
            "short_name": "Allen",
            "primary_email": "allen@example.edu",
        }
        user = CanvasUser.from_dict(data)
        assert user.id == 12345
        assert user.name == "Allen J Porter"
        assert user.sortable_name == "Porter, Allen J"
        assert user.short_name == "Allen"
        assert user.primary_email == "allen@example.edu"

    def test_canvas_user_from_dict_minimal(self) -> None:
        """Test CanvasUser deserialization with minimal dictionary."""
        data = {"id": 9999}
        user = CanvasUser.from_dict(data)
        assert user.id == 9999
        assert user.name == "User 9999"
        assert user.sortable_name is None
        assert user.short_name is None
        assert user.primary_email is None

    def test_canvas_observee_from_dict_full(self) -> None:
        """Test CanvasObservee deserialization with full attributes and root account IDs."""
        data = {
            "id": 6021,
            "name": "Quentin Porter",
            "sortable_name": "Porter, Quentin",
            "short_name": "Quentin",
            "pronouns": "He/Him",
            "observation_link_root_account_ids": [1, 2, 3],
        }
        observee = CanvasObservee.from_dict(data)
        assert observee.id == 6021
        assert observee.name == "Quentin Porter"
        assert observee.sortable_name == "Porter, Quentin"
        assert observee.short_name == "Quentin"
        assert observee.pronouns == "He/Him"
        assert observee.root_account_ids == (1, 2, 3)

    def test_canvas_observee_from_dict_minimal(self) -> None:
        """Test CanvasObservee deserialization with minimal dictionary."""
        data = {"id": 4899}
        observee = CanvasObservee.from_dict(data)
        assert observee.id == 4899
        assert observee.name == "Student 4899"
        assert observee.sortable_name is None
        assert observee.short_name is None
        assert observee.pronouns is None
        assert observee.root_account_ids == ()

    def test_canvas_term_from_dict_full(self) -> None:
        """Test CanvasTerm deserialization with ISO dates and custom workflow state."""
        data = {
            "id": 413,
            "name": "Fall 2026",
            "start_at": "2026-08-15T00:00:00Z",
            "end_at": "2026-12-20T23:59:59Z",
            "workflow_state": "active",
        }
        term = CanvasTerm.from_dict(data)
        assert term is not None
        assert term.id == 413
        assert term.name == "Fall 2026"
        assert term.start_at == datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert term.end_at == datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc)
        assert term.workflow_state == "active"

    def test_canvas_term_from_dict_minimal_and_invalid(self) -> None:
        """Test CanvasTerm deserialization with minimal dict and non-dict inputs."""
        term_min = CanvasTerm.from_dict({"id": 100})
        assert term_min is not None
        assert term_min.id == 100
        assert term_min.name == "Default Term"
        assert term_min.start_at is None
        assert term_min.end_at is None
        assert term_min.workflow_state == "active"

        assert CanvasTerm.from_dict(None) is None
        assert CanvasTerm.from_dict({}) is None
        assert CanvasTerm.from_dict([]) is None  # type: ignore[arg-type]
        assert CanvasTerm.from_dict("invalid") is None  # type: ignore[arg-type]

    def test_canvas_teacher_from_dict(self) -> None:
        """Test CanvasTeacher deserialization with full and minimal inputs."""
        data = {
            "id": 4857,
            "display_name": "Dr. Jon Asoulin",
            "avatar_image_url": "https://canvas.example.edu/avatar.png",
            "html_url": "https://canvas.example.edu/teachers/4857",
            "pronouns": "He/Him",
        }
        teacher = CanvasTeacher.from_dict(data)
        assert teacher.id == 4857
        assert teacher.display_name == "Dr. Jon Asoulin"
        assert teacher.avatar_image_url == "https://canvas.example.edu/avatar.png"
        assert teacher.html_url == "https://canvas.example.edu/teachers/4857"
        assert teacher.pronouns == "He/Him"

        teacher_min = CanvasTeacher.from_dict({"id": 111})
        assert teacher_min.id == 111
        assert teacher_min.display_name == "Teacher"
        assert teacher_min.avatar_image_url is None

    def test_canvas_grade_from_enrollment_dict(self) -> None:
        """Test CanvasGrade deserialization and letter grade fallback."""
        data = {
            "computed_current_score": "92.5",
            "computed_current_grade": "A-",
            "computed_final_score": 88.0,
            "computed_final_grade": "B+",
            "current_period_computed_current_score": "92.5",
            "current_period_computed_current_grade": "A-",
            "current_grading_period_title": "Semester 1",
        }
        grade = CanvasGrade.from_enrollment_dict(data)
        assert grade.current_score == 92.5
        assert grade.current_grade == "A-"
        assert grade.final_score == 88.0
        assert grade.final_grade == "B+"
        assert grade.current_period_score == 92.5
        assert grade.current_period_grade == "A-"
        assert grade.grading_period_title == "Semester 1"

        # Test fallback to computed_current_letter_grade when computed_current_grade is None
        fallback_data = {
            "computed_current_score": 75.0,
            "computed_current_grade": None,
            "computed_current_letter_grade": "C",
        }
        fallback_grade = CanvasGrade.from_enrollment_dict(fallback_data)
        assert fallback_grade.current_score == 75.0
        assert fallback_grade.current_grade == "C"

        # Empty dict -> all fields None
        empty_grade = CanvasGrade.from_enrollment_dict({})
        assert empty_grade.current_score is None
        assert empty_grade.current_grade is None

    def test_canvas_enrollment_from_dict(self) -> None:
        """Test CanvasEnrollment deserialization with embedded grade."""
        data = {
            "type": "student",
            "role": "StudentEnrollment",
            "user_id": 6021,
            "enrollment_state": "active",
            "computed_current_score": 95.0,
            "computed_current_grade": "A",
        }
        enrollment = CanvasEnrollment.from_dict(data)
        assert enrollment.type == "student"
        assert enrollment.role == "StudentEnrollment"
        assert enrollment.user_id == 6021
        assert enrollment.enrollment_state == "active"
        assert enrollment.grade.current_score == 95.0
        assert enrollment.grade.current_grade == "A"

    def test_canvas_course_from_dict_with_nested_structures(self) -> None:
        """Test CanvasCourse deserialization with nested term, teachers, and enrollments."""
        data = {
            "id": 7349,
            "name": "AP US History",
            "course_code": "APUSH-101",
            "account_id": 142,
            "start_at": "2026-08-15T00:00:00Z",
            "end_at": "2026-12-20T23:59:59Z",
            "workflow_state": "available",
            "term": {
                "id": 413,
                "name": "Fall 2026",
                "start_at": "2026-08-15T00:00:00Z",
                "end_at": "2026-12-20T23:59:59Z",
                "workflow_state": "active",
            },
            "teachers": [
                {
                    "id": 4857,
                    "display_name": "Dr. Jon Asoulin",
                    "avatar_image_url": "https://canvas.example.edu/avatar.png",
                },
                {"invalid": "no id field"},
            ],
            "enrollments": [
                {
                    "type": "student",
                    "role": "StudentEnrollment",
                    "user_id": 6021,
                    "enrollment_state": "active",
                    "computed_current_score": 92.5,
                    "computed_current_grade": "A-",
                }
            ],
        }
        course = CanvasCourse.from_dict(data)
        assert course.id == 7349
        assert course.name == "AP US History"
        assert course.course_code == "APUSH-101"
        assert course.account_id == 142
        assert course.start_at == datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert course.end_at == datetime(2026, 12, 20, 23, 59, 59, tzinfo=timezone.utc)
        assert course.workflow_state == "available"

        # Check nested term
        assert course.term is not None
        assert course.term.id == 413
        assert course.term.name == "Fall 2026"

        # Check teachers (invalid teacher without id should be filtered out)
        assert len(course.teachers) == 1
        assert course.teachers[0].id == 4857
        assert course.primary_teacher == course.teachers[0]

        # Check enrollments & primary_grade
        assert len(course.enrollments) == 1
        assert course.enrollments[0].user_id == 6021
        assert course.primary_grade == course.enrollments[0].grade
        assert course.primary_grade is not None
        assert course.primary_grade.current_score == 92.5

    def test_canvas_course_properties_empty_lists(self) -> None:
        """Test CanvasCourse primary_grade and primary_teacher properties with empty lists."""
        course = CanvasCourse(
            id=100,
            name="Empty Course",
            teachers=(),
            enrollments=(),
        )
        assert course.primary_grade is None
        assert course.primary_teacher is None

    def test_canvas_submission_from_dict_and_properties(self) -> None:
        """Test CanvasSubmission deserialization, flags, and properties."""
        data = {
            "id": 5196766,
            "assignment_id": 134664,
            "user_id": 6021,
            "workflow_state": "graded",
            "grade": "10",
            "score": 10.0,
            "excused": False,
            "missing": False,
            "late": False,
            "submitted_at": "2026-08-25T14:00:00Z",
            "graded_at": "2026-08-26T10:00:00Z",
            "submission_type": "online_text_entry",
        }
        sub = CanvasSubmission.from_dict(data)
        assert sub is not None
        assert sub.id == 5196766
        assert sub.assignment_id == 134664
        assert sub.user_id == 6021
        assert sub.workflow_state == "graded"
        assert sub.grade == "10"
        assert sub.score == 10.0
        assert sub.submitted_at == datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)
        assert sub.graded_at == datetime(2026, 8, 26, 10, 0, 0, tzinfo=timezone.utc)
        assert sub.is_graded_or_excused is True
        assert sub.is_submitted is True

        # Test unsubmitted & unassessed submission
        unsub_data = {
            "id": 5196767,
            "assignment_id": 134665,
            "user_id": 6021,
            "workflow_state": "unsubmitted",
            "grade": None,
            "score": None,
            "excused": False,
            "missing": True,
            "late": False,
            "submitted_at": None,
            "graded_at": None,
        }
        unsub = CanvasSubmission.from_dict(unsub_data)
        assert unsub is not None
        assert unsub.is_graded_or_excused is False
        assert unsub.is_submitted is False

        # Test excused submission
        excused_sub = CanvasSubmission.from_dict(
            {"id": 1, "excused": True, "workflow_state": "unsubmitted"}
        )
        assert excused_sub is not None
        assert excused_sub.is_graded_or_excused is True

        # Test submission with score
        score_sub = CanvasSubmission.from_dict(
            {"id": 2, "score": 8.5, "workflow_state": "unsubmitted"}
        )
        assert score_sub is not None
        assert score_sub.is_graded_or_excused is True

        # Test submission with grade letter
        grade_sub = CanvasSubmission.from_dict(
            {"id": 3, "grade": "B+", "workflow_state": "unsubmitted"}
        )
        assert grade_sub is not None
        assert grade_sub.is_graded_or_excused is True

        # Non-dict returns None
        assert CanvasSubmission.from_dict(None) is None
        assert CanvasSubmission.from_dict({}) is None
        assert CanvasSubmission.from_dict("invalid") is None  # type: ignore[arg-type]

    def test_canvas_assignment_from_dict_embedded_submission(self) -> None:
        """Test CanvasAssignment deserialization with embedded and explicit submission."""
        data = {
            "id": 134664,
            "course_id": 7349,
            "name": "Chapter 1 Reflection",
            "description": "<p>Write reflection</p>",
            "due_at": "2026-09-01T23:59:59Z",
            "lock_at": "2026-09-05T23:59:59Z",
            "unlock_at": "2026-08-20T00:00:00Z",
            "points_possible": "10.0",
            "grading_type": "points",
            "submission_types": ["online_text_entry", "online_upload"],
            "omit_from_final_grade": False,
            "workflow_state": "published",
            "html_url": "https://canvas.example.edu/assignments/134664",
            "submission": {
                "id": 5196766,
                "assignment_id": 134664,
                "user_id": 6021,
                "workflow_state": "unsubmitted",
            },
        }
        assignment = CanvasAssignment.from_dict(data)
        assert assignment.id == 134664
        assert assignment.course_id == 7349
        assert assignment.name == "Chapter 1 Reflection"
        assert assignment.description == "<p>Write reflection</p>"
        assert assignment.due_at == datetime(
            2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc
        )
        assert assignment.points_possible == 10.0
        assert assignment.submission_types == ("online_text_entry", "online_upload")
        assert assignment.workflow_state == "published"
        assert assignment.submission is not None
        assert assignment.submission.id == 5196766

        # Test explicit submission override
        custom_sub = CanvasSubmission(
            id=9999,
            assignment_id=134664,
            user_id=6021,
            workflow_state="graded",
            score=10.0,
        )
        assignment_custom = CanvasAssignment.from_dict(data, submission=custom_sub)
        assert assignment_custom.submission == custom_sub
        assert assignment_custom.submission is not None
        assert assignment_custom.submission.id == 9999

    def test_student_data_and_canvas_data_aggregation(self) -> None:
        """Test CanvasStudentData and CanvasData container structures."""
        user = CanvasUser(id=1, name="Parent User")
        student = CanvasObservee(id=6021, name="Student One")
        course = CanvasCourse(id=101, name="Math")
        assignment = CanvasAssignment(id=201, course_id=101, name="Homework 1")

        student_data = CanvasStudentData(
            student=student,
            courses=(course,),
            assignments=(assignment,),
        )
        assert student_data.student.id == 6021
        assert len(student_data.courses) == 1
        assert len(student_data.assignments) == 1

        canvas_data = CanvasData(
            user=user,
            observees=(student,),
            courses_by_student={6021: [course]},
            assignments_by_student={6021: [assignment]},
        )
        assert canvas_data.user.id == 1
        assert len(canvas_data.observees) == 1
        assert 6021 in canvas_data.courses_by_student
        assert 6021 in canvas_data.assignments_by_student


# ============================================================================
# Section 3: Tier 2 Boundary & Corner Cases Tests
# ============================================================================


class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary value analysis, missing/extra fields, and robust error handling."""

    def test_models_extra_unknown_fields_safely_ignored(self) -> None:
        """Test that unknown/unexpected JSON attributes from API are ignored cleanly."""
        user_data = {
            "id": 12345,
            "name": "Allen",
            "future_canvas_flag": True,
            "analytics_data": {"clicks": 42},
            "random_list": [1, 2, 3],
        }
        user = CanvasUser.from_dict(user_data)
        assert user.id == 12345
        assert user.name == "Allen"

        course_data = {
            "id": 7349,
            "name": "AP US History",
            "unknown_metadata": "some_value",
            "term": {
                "id": 413,
                "name": "Fall 2026",
                "custom_district_term_id": 99999,
            },
        }
        course = CanvasCourse.from_dict(course_data)
        assert course.id == 7349
        assert course.term is not None
        assert course.term.id == 413

    def test_models_explicit_null_values_in_payload(self) -> None:
        """Test models parse explicitly null / None fields without throwing exceptions."""
        course_data = {
            "id": 7349,
            "name": None,
            "course_code": None,
            "account_id": None,
            "start_at": None,
            "end_at": None,
            "workflow_state": None,
            "term": None,
            "teachers": None,
            "enrollments": None,
        }
        course = CanvasCourse.from_dict(course_data)
        assert course.id == 7349
        assert course.name == "Course 7349"
        assert course.course_code is None
        assert course.account_id is None
        assert course.start_at is None
        assert course.end_at is None
        assert course.workflow_state == "available"
        assert course.term is None
        assert course.teachers == ()
        assert course.enrollments == ()

    def test_models_empty_collections_and_arrays(self) -> None:
        """Test models parse empty lists as empty immutable tuples."""
        observee_data = {
            "id": 6021,
            "name": "Quentin",
            "observation_link_root_account_ids": [],
        }
        observee = CanvasObservee.from_dict(observee_data)
        assert observee.root_account_ids == ()

        assignment_data = {
            "id": 134664,
            "submission_types": [],
        }
        assignment = CanvasAssignment.from_dict(assignment_data)
        assert assignment.submission_types == ()

    def test_models_malformed_timestamps_handled_gracefully(self) -> None:
        """Test that malformed or garbage timestamp strings parse safely to None."""
        term_data = {
            "id": 100,
            "start_at": "2026-99-99T99:99:99Z",
            "end_at": "not-a-valid-date",
        }
        term = CanvasTerm.from_dict(term_data)
        assert term is not None
        assert term.start_at is None
        assert term.end_at is None

        asg_data = {
            "id": 200,
            "due_at": "INVALID_TIMESTAMP",
            "lock_at": "12345678",
            "unlock_at": "",
        }
        assignment = CanvasAssignment.from_dict(asg_data)
        assert assignment.due_at is None
        assert assignment.lock_at is None
        assert assignment.unlock_at is None

    def test_models_zero_and_negative_numeric_values(self) -> None:
        """Test models preserve zero and negative values for points and scores."""
        grade_data = {
            "computed_current_score": 0.0,
            "computed_final_score": -5.0,
            "current_period_computed_current_score": "0",
        }
        grade = CanvasGrade.from_enrollment_dict(grade_data)
        assert grade.current_score == 0.0
        assert grade.final_score == -5.0
        assert grade.current_period_score == 0.0

        assignment_data = {
            "id": 300,
            "points_possible": 0.0,
        }
        assignment = CanvasAssignment.from_dict(assignment_data)
        assert assignment.points_possible == 0.0

        submission_data = {
            "id": 400,
            "score": -2.5,
        }
        submission = CanvasSubmission.from_dict(submission_data)
        assert submission is not None
        assert submission.score == -2.5

    def test_models_unicode_and_special_character_fidelity(self) -> None:
        """Test model strings maintain full fidelity with Unicode, accents, emojis, and special chars."""
        unicode_user_data = {
            "id": 8888,
            "name": "Éléonore Müller 👩‍🏫",
            "sortable_name": "Müller, Éléonore",
            "primary_email": "müller@schüle.de",
        }
        user = CanvasUser.from_dict(unicode_user_data)
        assert user.name == "Éléonore Müller 👩‍🏫"
        assert user.sortable_name == "Müller, Éléonore"
        assert user.primary_email == "müller@schüle.de"

        unicode_course_data = {
            "id": 9999,
            "name": "Matemáticas y Español: Trigonometría & Álgebra 📐",
            "course_code": "MAT-101-ß",
        }
        course = CanvasCourse.from_dict(unicode_course_data)
        assert course.name == "Matemáticas y Español: Trigonometría & Álgebra 📐"
        assert course.course_code == "MAT-101-ß"


# ============================================================================
# Section 4: Slotted Frozen Dataclass Immutability Tests
# ============================================================================


class TestModelImmutability:
    """Verify that all Canvas data models are immutable frozen slotted dataclasses."""

    def test_canvas_user_immutability(self) -> None:
        """CanvasUser instances cannot be mutated."""
        user = CanvasUser(id=1, name="Original")
        with pytest.raises(FrozenInstanceError):
            user.name = "Mutated"  # type: ignore[misc]

    def test_canvas_observee_immutability(self) -> None:
        """CanvasObservee instances cannot be mutated."""
        observee = CanvasObservee(id=2, name="Student")
        with pytest.raises(FrozenInstanceError):
            observee.name = "Mutated"  # type: ignore[misc]

    def test_canvas_term_immutability(self) -> None:
        """CanvasTerm instances cannot be mutated."""
        term = CanvasTerm(id=3, name="Term 1")
        with pytest.raises(FrozenInstanceError):
            term.name = "Mutated"  # type: ignore[misc]

    def test_canvas_teacher_immutability(self) -> None:
        """CanvasTeacher instances cannot be mutated."""
        teacher = CanvasTeacher(id=4, display_name="Teacher")
        with pytest.raises(FrozenInstanceError):
            teacher.display_name = "Mutated"  # type: ignore[misc]

    def test_canvas_grade_immutability(self) -> None:
        """CanvasGrade instances cannot be mutated."""
        grade = CanvasGrade(current_score=90.0)
        with pytest.raises(FrozenInstanceError):
            grade.current_score = 100.0  # type: ignore[misc]

    def test_canvas_enrollment_immutability(self) -> None:
        """CanvasEnrollment instances cannot be mutated."""
        grade = CanvasGrade(current_score=90.0)
        enrollment = CanvasEnrollment(
            type="student",
            role="StudentEnrollment",
            user_id=10,
            enrollment_state="active",
            grade=grade,
        )
        with pytest.raises(FrozenInstanceError):
            enrollment.role = "TeacherEnrollment"  # type: ignore[misc]

    def test_canvas_course_immutability(self) -> None:
        """CanvasCourse instances cannot be mutated."""
        course = CanvasCourse(id=5, name="Course")
        with pytest.raises(FrozenInstanceError):
            course.name = "Mutated"  # type: ignore[misc]

    def test_canvas_submission_immutability(self) -> None:
        """CanvasSubmission instances cannot be mutated."""
        sub = CanvasSubmission(id=6, assignment_id=10, user_id=20)
        with pytest.raises(FrozenInstanceError):
            sub.score = 50.0  # type: ignore[misc]

    def test_canvas_assignment_immutability(self) -> None:
        """CanvasAssignment instances cannot be mutated."""
        asg = CanvasAssignment(id=7, course_id=5, name="Assignment")
        with pytest.raises(FrozenInstanceError):
            asg.name = "Mutated"  # type: ignore[misc]

    def test_canvas_student_data_immutability(self) -> None:
        """CanvasStudentData instances cannot be mutated."""
        student = CanvasObservee(id=1, name="Student")
        student_data = CanvasStudentData(student=student, courses=(), assignments=())
        with pytest.raises(FrozenInstanceError):
            student_data.student = CanvasObservee(id=2, name="Other")  # type: ignore[misc]

    def test_canvas_data_immutability(self) -> None:
        """CanvasData instances cannot be mutated."""
        user = CanvasUser(id=1, name="Parent")
        canvas_data = CanvasData(
            user=user,
            observees=(),
            courses_by_student={},
            assignments_by_student={},
        )
        with pytest.raises(FrozenInstanceError):
            canvas_data.user = CanvasUser(id=2, name="Other")  # type: ignore[misc]

    def test_models_have_slots_defined(self) -> None:
        """Verify __slots__ attribute is defined on all models for memory optimization."""
        assert hasattr(CanvasUser, "__slots__")
        assert hasattr(CanvasObservee, "__slots__")
        assert hasattr(CanvasTerm, "__slots__")
        assert hasattr(CanvasTeacher, "__slots__")
        assert hasattr(CanvasGrade, "__slots__")
        assert hasattr(CanvasEnrollment, "__slots__")
        assert hasattr(CanvasCourse, "__slots__")
        assert hasattr(CanvasSubmission, "__slots__")
        assert hasattr(CanvasAssignment, "__slots__")
        assert hasattr(CanvasStudentData, "__slots__")
        assert hasattr(CanvasData, "__slots__")

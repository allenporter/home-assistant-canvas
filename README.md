# Canvas LMS Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/allenporter/home-assistant-canvas)](https://github.com/allenporter/home-assistant-canvas/releases)
[![Test](https://github.com/allenporter/home-assistant-canvas/actions/workflows/test.yaml/badge.svg)](https://github.com/allenporter/home-assistant-canvas/actions/workflows/test.yaml)
[![Lint](https://github.com/allenporter/home-assistant-canvas/actions/workflows/lint.yaml/badge.svg)](https://github.com/allenporter/home-assistant-canvas/actions/workflows/lint.yaml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Home Assistant custom component that integrates with **Instructure Canvas LMS** to track academic progress, grades, actionable assignments, and course calendars for students and observing parents.

---

## Features

- 🎓 **Multi-Student Auto-Discovery**:

  - Automatically discovers all observed students for parent accounts, or connects directly to a student login.
  - Registers distinct **Device Profiles** in Home Assistant's Device Registry for each student.

- 📊 **Real-Time Grade Sensors (`sensor`)**:

  - Monitors current score percentages (`%`) and letter grades (e.g., `A-`, `B+`) per course.
  - Tracks instructor name, course code, academic term, and grading period title as entity attributes.

- ✅ **Actionable To-Do Lists (`todo`)**:

  - Creates an interactive To-Do list per student (`todo.<student>_assignments`).
  - **Chronologically Sorted**: Orders upcoming deadlines and overdue tasks chronologically.
  - **Smart In-Class Noise Filter**: Filters out 5-minute bell-ringers (_Do Nows_), lecture guided notes, and in-class period rehearsals, while preserving real homework (both online uploads and physical paper worksheets).
  - **Interactive Check-Offs**: Mark assignments complete or add manual study tasks directly within Home Assistant.

- 📅 **Classroom Learning Calendars (`calendar`)**:

  - Maps assignment due dates, daily classroom topics, and project deadlines directly to Home Assistant's Calendar view (`calendar.<student>_assignments`).
  - Supports datetime range queries and upcoming event sensors.

- 🛡️ **Intelligent Heuristics & Noise Filtering**:
  - Filters out archived, concluded, or placeholder courses.
  - Excludes pre-term cloned syllabus templates and already graded/excused submissions.

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Click the three dots in the top-right corner and select **Custom repositories**.
4. Enter `https://github.com/allenporter/home-assistant-canvas` and select **Integration** as the category.
5. Search for **Canvas**, click **Download**, and restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the [Releases page](https://github.com/allenporter/home-assistant-canvas/releases).
2. Copy the `custom_components/canvas` folder into your Home Assistant `<config>/custom_components/` directory:
   ```bash
   cp -r custom_components/canvas /path/to/homeassistant/config/custom_components/
   ```
3. Restart Home Assistant.

---

## Configuration

### 1. Find Your Canvas Base URL

Locate the web address you use to sign in to Canvas:

- Standard Instructure URL: `https://<school-name>.instructure.com`
- Custom District Domain: `https://canvas.<district>.edu`

### 2. Generate a Personal Access Token

1. Log in to your Canvas LMS account.
2. In the left navigation menu, click **Account** > **Settings**.
3. Scroll down to the **Approved Integrations** section.
4. Click **+ New Access Token**.
5. Enter a purpose (e.g., `Home Assistant`) and click **Generate Token**.
6. Copy the generated token string.

### 3. Add Integration in Home Assistant

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Canvas**.
3. Enter your **Canvas Base URL** and paste your **Access Token**.
4. Click **Submit**.

---

## Supported Entities & Devices

| Platform   | Entity Pattern                    | Description                                                         |
| :--------- | :-------------------------------- | :------------------------------------------------------------------ |
| `sensor`   | `sensor.<student>_<course>_grade` | Course grade sensor (% state, letter grade, instructor, term).      |
| `todo`     | `todo.<student>_assignments`      | Interactive, chronologically sorted list of pending homework.       |
| `calendar` | `calendar.<student>_assignments`  | Assignment deadlines and classroom learning topics on the calendar. |

---

## Development & Testing

This project uses modern Python development tooling with `uv`, `pytest`, `ruff`, and `ty`.

### Environment Setup

```bash
# Bootstrap virtual environment and tools
./script/bootstrap

# Install dependencies and pre-commit hooks
./script/setup
```

### Running Tests & Quality Checks

```bash
# Run complete test suite with coverage
./script/test

# Run linters (ruff, ty check, codespell, yamllint, prettier)
./script/lint

# Start local Home Assistant development server
./script/server
```

---

## License

This project is licensed under the [Apache 2.0 License](LICENSE).

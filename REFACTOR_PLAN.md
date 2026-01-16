# Ralph TUI Simplification Plan

## Goal
Replace complex multi-screen TUI with simple numbered menu launcher.

## Current State (to remove/simplify)
- `ralph/tui/screens/folder_browser.py` - 283 lines (DELETE)
- `ralph/tui/screens/new_project.py` - 307 lines (SIMPLIFY to text input)
- `ralph/tui/screens/project_select.py` - 528 lines (REPLACE with simple menu)
- `ralph/tui/screens/ai_config.py` - (SKIP on startup, make optional)

## Target UX
```
╔══════════════════════════════════════════════════╗
║             Ralph Project Manager                 ║
╠══════════════════════════════════════════════════╣
║  Recent Projects:                                 ║
║    [1] MyProject         C:\dev\myproject         ║
║        12/20 tasks (60%)                          ║
║    [2] WebApp            C:\dev\webapp            ║
║        5/15 tasks (33%)                           ║
║  ─────────────────────────────────────────────────║
║    [N] New project                                ║
║    [Q] Quit                                       ║
╚══════════════════════════════════════════════════╝
Select: _
```

New project flow:
```
Type: [G]reenfield / [B]rownfield: B
Path: C:\dev\existing-project
Name [existing-project]: My Project
Created!
```

---

## Wave 1: Foundation (Parallel)

### Task 1A: Add recent.json storage
File: `ralph/storage.py`
- Add `RECENT_FILE = Path(__file__).parent.parent / "recent.json"`
- Add `load_recent() -> list[str]` - returns list of project IDs ordered by last access
- Add `update_recent(project_id: str)` - moves project to top of recent list
- Add `get_projects_by_recent() -> list[Project]` - returns projects ordered by recent access
- Keep max 10 recent entries

### Task 1B: Create simple launcher screen
File: `ralph/tui/screens/launcher.py` (NEW)
- Simple Textual screen with Static text display
- Show numbered list of recent projects with progress
- Input widget for selection (1-9, N, Q)
- Handle selection: number opens project, N creates new, Q quits
- For "N": prompt for type (G/B), path (text input), name (text input with default)
- No folder browser - just type the path

---

## Wave 2: Integration (Parallel)

### Task 2A: Update entry point
File: `ralph_tui.py`
- Simplify to just launch the app
- Remove --list functionality (launcher shows this)

### Task 2B: Update app.py
File: `ralph/tui/app.py`
- Remove AI config screen from startup flow
- `on_mount()` should push LauncherScreen directly
- Remove `_show_project_select_or_main()` complexity
- Add method to handle launcher selection and push MainScreen

---

## Wave 3: Cleanup (Parallel)

### Task 3A: Delete folder_browser.py
- Remove `ralph/tui/screens/folder_browser.py`
- Update `ralph/tui/screens/__init__.py` to remove export

### Task 3B: Delete old project screens
- Remove `ralph/tui/screens/project_select.py`
- Remove `ralph/tui/screens/new_project.py`
- Update `ralph/tui/screens/__init__.py`

### Task 3C: Remove browser functions from storage
- Remove `browse_folder()` function from storage.py
- Remove `get_drives()` function from storage.py
- Remove `FolderEntry` from models if unused elsewhere

---

## Wave 4: Test
- Run `python ralph_tui.py`
- Verify numbered selection works
- Verify new project creation works
- Verify main task screen loads correctly

---
description: Create handoff document for transferring work to another session
---

# Create Handoff

You are tasked with creating a handoff document to transfer your work to another agent/session. This preserves all context so work can continue seamlessly.

## When to Use

- Context window running low
- Ending work session for the day
- Complex phase spanning multiple sessions
- Before making breaking changes (checkpoint)

## Usage

```
/create_handoff
```

No parameters needed - automatically captures current state.

## Process

### Step 1: Gather Current State

Collect information about:

1. **Current Phase** - Which phase from IMPLEMENTATION_PHASES.md
2. **Todo Status** - What's done, in progress, pending
3. **Files Changed** - All modifications made this session
4. **Issues Found** - Problems encountered and solutions
5. **Learnings** - Important discoveries about the codebase

### Step 2: Create Handoff Directory

```
frontend/feature_implementation/handoffs/
└── PHASE_N/
    └── YYYY-MM-DD_HH-MM-SS_description.md
```

Example: `frontend/feature_implementation/handoffs/PHASE_3/2026-02-05_14-30-00_chunking_in_progress.md`

### Step 3: Write Handoff Document

Use this template:

```markdown
---
date: [ISO timestamp with timezone]
phase: [Phase number and name]
status: [in_progress / blocked / ready_for_review]
last_updated: [YYYY-MM-DD]
---

# Handoff: Phase [N] - [Brief Description]

## Current Status

**Phase:** [N] - [Phase Name]
**Progress:** [X]% complete ([Y] of [Z] steps done)
**Status:** [in_progress / blocked / paused]

## Task Summary

| Task | Status | Notes |
|------|--------|-------|
| [Task 1] | ✅ Done | [file:line reference] |
| [Task 2] | ✅ Done | [file:line reference] |
| [Task 3] | 🔄 In Progress | [current state] |
| [Task 4] | ⬜ Pending | [blocked by X / ready] |

## Files Changed This Session

### New Files
| File | Purpose | Lines |
|------|---------|-------|
| `path/to/file.py` | [description] | [count] |

### Modified Files
| File | Changes | Lines |
|------|---------|-------|
| `path/to/file.py:100-150` | [description] | [count] |

## Current Work State

### What I Was Working On
[Detailed description of current task]

### Where I Stopped
[Exact point - file:line, function name, etc.]

### Next Immediate Step
[Very specific next action to take]

```python
# Code snippet showing where to continue (if helpful)
# Example: This function needs the loop completed
def process_chunks():
    for chunk in chunks:
        # TODO: Add cell_grounding extraction here
        pass
```

## Critical Context

### Plan Files Being Used
- `frontend/feature_implementation/[FILE1].md` - [what from it]
- `frontend/feature_implementation/[FILE2].md` - [what from it]

### Key Decisions Made
1. [Decision] - [Why]
2. [Decision] - [Why]

### Assumptions
- [Assumption 1]
- [Assumption 2]

## Issues & Blockers

### Resolved Issues
| Issue | Resolution |
|-------|------------|
| [Problem] | [How fixed] |

### Open Issues
| Issue | Impact | Suggested Fix |
|-------|--------|---------------|
| [Problem] | [blocks X] | [possible solution] |

## Learnings

### Code Patterns Discovered
- [Pattern in existing code that should be followed]
- [Helper function that's useful]

### Gotchas
- [Something unexpected about the codebase]
- [Edge case to watch for]

### Important File Locations
- [file:line] - [why it's important]
- [file:line] - [why it's important]

## Action Items for Next Session

### Immediate (Continue Current Work)
1. [ ] [Specific task with file:line reference]
2. [ ] [Specific task with file:line reference]

### Short-term (Complete Phase)
3. [ ] [Task]
4. [ ] [Task]

### Before Completion
5. [ ] Run verification checks
6. [ ] Update IMPLEMENTATION_PHASES.md
7. [ ] Test integration with existing code

## How to Resume

```bash
# 1. Read this handoff document
/resume_handoff frontend/feature_implementation/handoffs/PHASE_N/[this_file].md

# 2. Or manually:
# - Read IMPLEMENTATION_PHASES.md for context
# - Check todo list status
# - Continue from "Next Immediate Step" above
```

## Environment Notes

### Servers/Services Running
- [Service] at [URL/port]

### Test Data Used
- [Description of test files used]

### Credentials/Config
- [Any session-specific config to note]

---
*Handoff created: [timestamp]*
*Session duration: ~[X] hours*
*Estimated remaining for phase: [Y] hours*
```

### Step 4: Verify Handoff Quality

Check that handoff includes:
- [ ] Clear current status (which phase, how far)
- [ ] Exact stopping point (file:line)
- [ ] All files changed listed
- [ ] Next steps are specific and actionable
- [ ] Blockers clearly documented
- [ ] Key learnings captured

### Step 5: Report to User

```
## Handoff Created ✅

**Location:** `frontend/feature_implementation/handoffs/PHASE_[N]/[filename].md`

### Summary
- Phase: [N] - [Name]
- Progress: [X]%
- Status: [in_progress/blocked]

### To Resume
In a new session, run:
```bash
/resume_handoff frontend/feature_implementation/handoffs/PHASE_[N]/[filename].md
```

### Key Points for Next Session
1. [Most important thing to know]
2. [Second most important]
3. [Third most important]

---
Safe to end session. All context preserved.
```

## Quick Handoff (Emergency)

If context is about to run out, create minimal handoff:

```markdown
# QUICK HANDOFF - Phase [N]

**Status:** [X]% done
**Stopped at:** [file:line]
**Next step:** [one sentence]

**Files changed:**
- [file1]
- [file2]

**Resume:** Read IMPLEMENTATION_PHASES.md, continue from [step]
```

## Notes

- Create handoff BEFORE context runs out
- Be specific - vague handoffs waste time
- Include file:line references, not just file names
- Note any temporary changes or debug code left in
- Mention if any services need to be running

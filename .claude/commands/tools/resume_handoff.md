---
description: Resume work from a handoff document created in a previous session
---

# Resume Handoff

You are tasked with resuming work from a previous session's handoff document. This command restores context and continues implementation seamlessly.

## Usage

```
/resume_handoff <path_to_handoff_file>
```

Example:
```
/resume_handoff frontend/feature_implementation/handoffs/PHASE_3/2026-02-05_14-30-00_chunking_in_progress.md
```

## Process

### Step 1: Load Handoff Document

1. **Read the handoff file completely** - no limit/offset
2. **Extract key information:**
   - Current phase and progress
   - Exact stopping point
   - Files changed
   - Open issues/blockers
   - Next immediate steps

### Step 2: Verify Current State

Check that handoff is still valid:

```
## Handoff Validation

### File Check
| File in Handoff | Current Status |
|-----------------|----------------|
| `path/to/file.py` | ✅ Exists / ⚠️ Modified / ❌ Missing |

### Code State Check
- [ ] Files match handoff description
- [ ] No conflicting changes made
- [ ] Dependencies still in place

### Issues Check
- [ ] Reported blockers still exist (or resolved?)
- [ ] New issues introduced?
```

If discrepancies found:
```
⚠️ HANDOFF MISMATCH

The codebase has changed since handoff was created:

| What Changed | Handoff Says | Current State |
|--------------|--------------|---------------|
| [file/feature] | [expected] | [actual] |

Options:
A) Proceed with adjusted plan
B) Investigate changes first
C) Create new handoff from current state

Recommendation: [A/B/C]
```

### Step 3: Load Supporting Context

Read additional files mentioned in handoff:

1. **IMPLEMENTATION_PHASES.md** - Current phase status
2. **Plan files** - Referenced in "Critical Context" section
3. **Modified files** - Quick scan of changes made

### Step 4: Restore Todo List

Create todo list from handoff's "Action Items":

```
Restoring todo list from handoff...

- ✅ [Completed task from handoff]
- ✅ [Completed task from handoff]
- 🔄 [In progress task - RESUMING HERE]
- ⬜ [Pending task]
- ⬜ [Pending task]
```

### Step 5: Present Resume Summary

```
## Session Resumed from Handoff ✅

### Previous Session
- **Date:** [handoff date]
- **Phase:** [N] - [Name]
- **Progress:** [X]% ([Y] of [Z] steps)

### Handoff Validation
- Files: ✅ All present and unchanged
- Code state: ✅ Matches handoff
- Blockers: [✅ Resolved / ⚠️ Still open]

### Where We Left Off
**File:** `[file:line]`
**Task:** [description]
**Next step:** [specific action]

### Learnings from Previous Session
- [Key learning 1]
- [Key learning 2]

### Open Issues to Address
1. [Issue if any]

### Todo List Restored
[Show current todo list]

---

Ready to continue. Starting from: [exact task/step]

Proceed? (yes / show more context / investigate [issue])
```

### Step 6: Continue Implementation

Once user confirms:

1. Mark first pending todo as `in_progress`
2. Navigate to the stopping point mentioned in handoff
3. Continue implementation following `/implement_phase` workflow
4. Reference learnings from handoff to avoid repeating mistakes

## Handling Common Scenarios

### Scenario 1: Clean Resume
```
Handoff valid, no changes detected.
Continuing from: [file:line]
Next action: [specific step]
```

### Scenario 2: Minor Changes
```
⚠️ Minor changes detected:
- [file] has new imports (non-conflicting)

These don't affect handoff context. Proceeding.
```

### Scenario 3: Significant Changes
```
🔴 Significant changes detected:
- [file] structure changed substantially
- Handoff references code that no longer exists

Recommendation:
1. Review changes with user
2. Create new analysis with /start_phase
3. Or manually adjust and continue
```

### Scenario 4: Blocker Resolved
```
✅ Good news! Blocker from handoff is resolved:
- Issue: [what was blocked]
- Resolution: [what changed]

Can now proceed with previously blocked task.
```

### Scenario 5: New Blocker
```
🔴 New blocker discovered:
- [file] now has breaking changes
- Impact: [how it affects our work]

Need to address before continuing.
```

## Quick Resume Checklist

```
## Resume Checklist

### Context Loaded
- [ ] Handoff document read completely
- [ ] IMPLEMENTATION_PHASES.md checked
- [ ] Plan files reviewed (from handoff references)

### Validation Done
- [ ] Files exist and match
- [ ] No conflicting changes
- [ ] Blockers status checked

### Ready to Continue
- [ ] Todo list restored
- [ ] Exact resume point identified
- [ ] User confirmed to proceed
```

## Finding Handoffs

If user doesn't provide path, search for recent handoffs:

```bash
# List available handoffs
ls frontend/feature_implementation/handoffs/

# By phase
ls frontend/feature_implementation/handoffs/PHASE_3/

# Most recent
ls -t frontend/feature_implementation/handoffs/*/
```

Present options:
```
## Available Handoffs

| Date | Phase | File | Status |
|------|-------|------|--------|
| 2026-02-05 14:30 | Phase 3 | chunking_in_progress.md | in_progress |
| 2026-02-04 17:00 | Phase 2 | chat_history_complete.md | completed |

Which handoff to resume? (Enter number or path)
```

## Notes

- Always validate handoff before trusting it
- If >24 hours old, extra validation recommended
- Check git log for changes since handoff date
- When in doubt, re-run `/start_phase` for fresh analysis
- Keep handoff file for reference even after resuming

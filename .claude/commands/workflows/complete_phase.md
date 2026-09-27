---
description: Complete a phase with verification, documentation update, and status change
---

# Complete Phase

You are tasked with completing and documenting a finished implementation phase. This command ensures all work is verified and documentation stays in sync.

## Prerequisites

- Implementation must be complete (all todos done)
- Code must compile without errors
- User has confirmed implementation is working

## Usage

```
/complete_phase <phase_number>
```

## Process

### Step 1: Final Verification

Run comprehensive checks:

```
## Final Verification - Phase [N]

### Code Quality Checks
- [ ] No syntax errors in new files
- [ ] No TypeScript errors: `npm run build` (frontend)
- [ ] No Python errors: `python -m py_compile <files>` (backend)
- [ ] No linting errors (if linter configured)

### Integration Checks
- [ ] New code imports work correctly
- [ ] Existing functionality not broken
- [ ] API endpoints respond correctly (if applicable)

### Functionality Checks
- [ ] Primary feature works as expected
- [ ] Edge cases handled
- [ ] Error handling in place

### Test Results (if applicable)
- [ ] Unit tests pass
- [ ] Integration tests pass
```

### Step 2: Document Changes

Create a summary of what was implemented:

```
## Phase [N] Completion Summary

### What Was Implemented
[Brief description of the feature/functionality]

### Files Created
| File | Purpose | Lines |
|------|---------|-------|
| `path/to/file.py` | [description] | [count] |

### Files Modified
| File | Changes | Lines Changed |
|------|---------|---------------|
| `path/to/file.py` | [description] | [count] |

### Key Functions/Components
- `function_name()` in `file.py` - [purpose]
- `ComponentName` in `file.tsx` - [purpose]

### Database Changes (if any)
- New table: [name]
- New column: [table.column]
- New index: [name]

### API Changes (if any)
- New endpoint: `POST /api/...`
- Modified endpoint: `GET /api/...`

### Configuration Changes (if any)
- New env variable: `VAR_NAME`
- Updated config: `file.json`
```

### Step 3: Update IMPLEMENTATION_PHASES.md

Make the following updates to `frontend/feature_implementation/IMPLEMENTATION_PHASES.md`:

#### 3.1 Update Quick Status Overview Table

Change the completed phase:
```markdown
| **Phase N** | [Name] | ✅ DONE | [files] |
```

Change the next phase:
```markdown
| **Phase N+1** | [Name] | 🔲 NEXT | [files] |
```

#### 3.2 Update Phase Section

Add completion details to the phase section:

```markdown
## Phase N: [Name] ✅ COMPLETED

> **Completed:** [Current Date - February X, 2026]

### What Was Implemented

[Summary from Step 2]

### Backend Files
| Feature | File | Status |
|---------|------|--------|
| [Feature] | `path/to/file.py` | ✅ Done |

### Frontend Files (if applicable)
| Feature | File | Status |
|---------|------|--------|
| [Feature] | `path/to/file.tsx` | ✅ Done |

### Key Implementation Details
- [Important detail 1]
- [Important detail 2]
- [Any gotchas or special handling]
```

#### 3.3 Update Document Metadata

At the bottom of IMPLEMENTATION_PHASES.md:
```markdown
*Last Updated: [Current Date]*
*Next Action: Start Phase [N+1] ([Phase Name])*
```

### Step 4: Create Phase Completion Record

Create a completion record in `frontend/feature_implementation/completed/`:

```
frontend/feature_implementation/completed/
└── PHASE_N_COMPLETION.md
```

With content:
```markdown
# Phase [N]: [Name] - Completion Record

**Completed:** [Date]
**Duration:** [Estimated time spent]

## Summary
[What was implemented]

## Files Changed
[List with line references]

## Testing Done
[How it was verified]

## Known Limitations
[Any limitations or future improvements needed]

## Dependencies for Next Phase
[What Phase N+1 needs from this phase]
```

### Step 5: Git Commit (if requested)

If user wants to commit:

```bash
git add .
git commit -m "Complete Phase [N]: [Phase Name]

- [Key change 1]
- [Key change 2]
- [Key change 3]

Implements: [brief description]
Next: Phase [N+1] - [Name]"
```

### Step 6: Report Completion

```
## Phase [N] Complete! ✅

### Summary
- Files created: [X]
- Files modified: [Y]
- Lines of code: [Z]

### Documentation Updated
- ✅ IMPLEMENTATION_PHASES.md status changed to DONE
- ✅ Completion record created
- ✅ Next phase marked as NEXT

### Next Steps
Phase [N+1]: [Name] is ready to start.

Run `/start_phase [N+1]` when ready to continue.

### Notes for Next Phase
[Any important context for Phase N+1]
```

## Checklist Template

Use this checklist before marking complete:

```
## Phase [N] Completion Checklist

### Implementation
- [ ] All todo items completed
- [ ] All planned features implemented
- [ ] Code follows project conventions

### Quality
- [ ] No compilation errors
- [ ] No runtime errors in basic testing
- [ ] Error handling in place

### Documentation
- [ ] IMPLEMENTATION_PHASES.md updated
- [ ] Code comments where needed (minimal)
- [ ] Completion record created

### Integration
- [ ] Works with existing code
- [ ] Doesn't break other features
- [ ] Ready for next phase to build on

### User Confirmation
- [ ] User tested and approved
- [ ] Any feedback addressed
```

## Rollback Information

In case phase needs to be reverted, document:

```
### Rollback Instructions (if needed)

Files to remove:
- path/to/new/file.py

Files to restore:
- path/to/modified/file.py (restore lines X-Y)

Database changes to undo:
- DROP TABLE [if created]
- Remove column [if added]
```

## Notes

- Never mark phase complete without user confirmation
- Always update IMPLEMENTATION_PHASES.md - this is the source of truth
- Create completion record for future reference
- Document any workarounds or technical debt
- Note dependencies for next phase clearly

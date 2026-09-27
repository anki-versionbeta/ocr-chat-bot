---
description: Implement a phase with continuous validation and mismatch detection
---

# Implement Phase

You are tasked with implementing an approved phase from IMPLEMENTATION_PHASES.md. This command guides implementation with continuous validation.

## Prerequisites

- Must have run `/start_phase <N>` first
- User must have confirmed "proceed" after analysis
- All critical issues must be resolved

## Usage

```
/implement_phase <phase_number>
```

Or continue from current todo list if already in progress.

## Implementation Philosophy

Plans are carefully designed, but reality can be messy. Your job is to:
- Follow the plan's intent while adapting to what you find
- Implement each step fully before moving to the next
- Verify your work makes sense in the broader codebase context
- STOP and report when something doesn't match the plan

## Process

### Step 1: Load Context

1. **Read current todo list** - identify in_progress and pending items
2. **Read relevant plan files** - refresh understanding
3. **Check IMPLEMENTATION_PHASES.md** - verify current phase status

### Step 2: Implement Step by Step

For each implementation step:

#### Before Coding
```
Starting: [Step description]
Target: [file path or component]
Expected outcome: [what this step achieves]
```

#### During Coding
- Write clean, well-structured code
- Follow existing patterns in the codebase
- Add minimal comments only where logic isn't self-evident
- Don't over-engineer - implement exactly what's needed

#### After Each Step
```
✅ Completed: [Step description]
Changes made:
- [file:line] - [description of change]
- [file:line] - [description of change]

Verification:
- [x] Code compiles/no syntax errors
- [x] Follows existing patterns
- [ ] Tested (if applicable)
```

### Step 3: Handle Mismatches

When something doesn't match the plan:

```
⚠️ MISMATCH DETECTED

Step: [Current step]
Issue: [What doesn't match]

Plan says:
[Quote from plan]

Found in codebase:
[What actually exists]

Why this matters:
[Impact on implementation]

Options:
A) [Adjust implementation to work with actual code]
B) [Update plan to reflect reality]
C) [Need clarification from user]

Recommended: [A/B/C] because [reason]

How should I proceed?
```

**STOP and wait for user response before continuing.**

### Step 4: Update Progress

After completing each step:

1. **Update todo list** - mark completed, move to next
2. **Track changes** - maintain list of modified files
3. **Note learnings** - anything unexpected discovered

### Step 5: Verification Checkpoints

After every 2-3 steps, run verification:

```
## Verification Checkpoint

### Code Quality
- [ ] No syntax errors
- [ ] No TypeScript/Python type errors
- [ ] Follows project conventions

### Functionality
- [ ] New code integrates with existing code
- [ ] No broken imports
- [ ] Dependencies available

### Run Commands (if applicable)
- [ ] `npm run build` (frontend)
- [ ] `python -m py_compile <file>` (backend)
- [ ] Tests pass (if tests exist)

Issues found: [None / List issues]
```

## Data Structures Reference (Phase 3)

When implementing Phase 3, use these exact structures:

### Table Chunk
```python
{
    "document_id": "uuid",
    "process_id": "uuid",
    "chunk_id": "doc_uuid_chunk_5",
    "chunk_type": "table",
    "chunk_index": 5,
    "page": 2,
    "content": "Test | Spec | Result\npH | 5.5-6.5 | 6.1",
    "cell_grounding": {
        "1-31": {"bbox": {"left": 0.5, "top": 0.3, "width": 0.1, "height": 0.02}, "text": "6.1", "row": 7, "col": 3}
    },
    "markdown": "<table id='1-t0'><tr><td id='1-31'>6.1</td></tr></table>",
    "bbox_left": 0.13,
    "bbox_top": 0.30,
    "bbox_right": 0.87,
    "bbox_bottom": 0.65,
    "layout_type": "TABLE"
}
```

### Text Chunk
```python
{
    "document_id": "uuid",
    "process_id": "uuid",
    "chunk_id": "doc_uuid_chunk_3",
    "chunk_type": "text",
    "chunk_index": 3,
    "page": 1,
    "content": "Batch #: 1000459079\nProduction Date: 17 Sept 2021",
    "line_grounding": {
        "uuid-abc": {"bbox": {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.02}, "text": "Batch #: 1000459079"}
    },
    "layout_type": "SECTION_HEADER",
    "bbox_left": 0.10,
    "bbox_top": 0.20,
    "bbox_right": 0.40,
    "bbox_bottom": 0.24
}
```

## Error Handling

### Syntax Error
```
❌ Error in [file]:[line]
Error: [error message]
Fix: [corrected code]
```

### Import Error
```
❌ Import Error: [module] not found
Check: Is it installed? Is the path correct?
Fix: [solution]
```

### Logic Error
```
❌ Logic Issue Detected
Expected behavior: [what should happen]
Actual behavior: [what happens]
Root cause: [analysis]
Fix: [solution]
```

## Progress Tracking

Maintain running progress in this format:

```
## Phase [N] Implementation Progress

### Completed Steps
✅ Step 1: [description] - [files changed]
✅ Step 2: [description] - [files changed]

### Current Step
🔄 Step 3: [description]
   - [x] Sub-task A
   - [ ] Sub-task B
   - [ ] Sub-task C

### Pending Steps
⬜ Step 4: [description]
⬜ Step 5: [description]

### Files Modified
- backend/services/textract_parser.py (new)
- backend/services/chunk_transformer.py (new)
- backend/app.py:1270-1520 (modified)

### Issues Encountered
1. [Issue] - [Resolution]

### Learnings
- [Important discovery]
```

## Completion Criteria

Phase is complete when:
1. All steps in todo list marked ✅
2. All verification checkpoints pass
3. No unresolved mismatches
4. Code integrates cleanly with existing codebase

Then prompt user:
```
Phase [N] implementation complete!

Summary:
- [X] files created
- [Y] files modified
- [Z] total lines of code

Next: Run `/complete_phase [N]` to update documentation and mark phase done.
```

## Notes

- Never skip steps even if they seem simple
- Always verify code compiles before moving on
- Keep changes focused - don't refactor unrelated code
- If context is running low, run `/create_handoff` before losing progress
- Ask for clarification rather than guessing

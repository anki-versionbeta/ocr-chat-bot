---
description: Start a new implementation phase with full analysis and validation
---

# Start Phase

You are tasked with starting a new implementation phase from the OCR RAG System. This command performs thorough analysis before any coding begins.

## Usage

```
/start_phase <phase_number>
```

Example: `/start_phase 3` to start Phase 3 (Textract Chunking Pipeline)

## Process

### Step 1: Load Phase Information

1. **Read IMPLEMENTATION_PHASES.md** completely:
   ```
   frontend/feature_implementation/IMPLEMENTATION_PHASES.md
   ```

2. **Identify the requested phase** from the Quick Status Overview table

3. **Verify phase is ready to start**:
   - Check if previous phases are marked ✅ DONE
   - If prerequisites incomplete, STOP and report

### Step 2: Read All Plan Files

For the identified phase, read ALL files listed in "Plan Files to Reference":

**Phase 3 (Textract Chunking Pipeline):**
- `frontend/feature_implementation/COMPLETE_CHUNKING_STRATEGY.md`
- `frontend/feature_implementation/TRANSFORMATION_OF_CELL_GROUNDING.md`
- `frontend/feature_implementation/TRANSFORMATION_OF_LINE_BLOCKS.md`
- `frontend/feature_implementation/COMPLETE_RAG_FLOW_WITH_BBOX.md`

**Phase 4 (RAG Search & Query):**
- `frontend/feature_implementation/RAG_QUERY_EXTRACTION_STRATEGY.md`
- `frontend/feature_implementation/CORRECTED_RAG_QUERY_FLOWS.md`
- `frontend/feature_implementation/COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md`
- `frontend/feature_implementation/BBOX_MATCHING_STRATEGY.md`

**Phase 5 (PDF Viewer & Highlighting):**
- `frontend/feature_implementation/PDF_VIEWER_CHAT_INTEGRATION.md`
- `frontend/feature_implementation/BBOX_HIGHLIGHT_IMPLEMENTATION.md`
- `frontend/feature_implementation/LANDING_AI_VS_OUR_APPROACH_DETAILED.md`

**Phase 6 (Neo4j Structural Integration):**
- `frontend/feature_implementation/NEO4J_DEEP_INTEGRATION_ANALYSIS.md`
- `frontend/feature_implementation/NEO4J_USE_CASES_ANALYSIS.md`
- `frontend/feature_implementation/BEST_LIBRARY_FOR_NEO4J.md`
- `frontend/feature_implementation/dbschemas/PHASE3_NEO4J_SCHEMA.md`

**IMPORTANT:** Read files FULLY - never use limit/offset parameters.

### Step 3: Analyze Current Codebase

Cross-reference plan assumptions with actual code:

1. **Check file references in plan:**
   - Do referenced files exist?
   - Are line numbers still accurate?
   - Has code structure changed?

2. **Verify dependencies:**
   - Are required tables/schemas created?
   - Are required packages installed?
   - Are referenced functions present?

3. **Check for conflicts:**
   - Will changes conflict with existing code?
   - Are there uncommitted changes in target files?

### Step 4: Report Findings

Present analysis in this format:

```
## Phase [N]: [Phase Name] - Analysis Complete

### Prerequisites Check
- ✅ Phase [N-1] completed
- ✅ Required tables exist: [list]
- ⚠️ Issue: [if any]

### Plan Files Reviewed
1. [filename] - [key points]
2. [filename] - [key points]
...

### Codebase Validation
| Plan Reference | Status | Notes |
|----------------|--------|-------|
| app.py:1270-1520 | ✅ Found | RecursiveCharacterTextSplitter present |
| backend/services/ | ✅ Exists | Target folder ready |
| Weaviate schema | ⚠️ Issue | Missing 4 properties |

### Issues Found
1. **[Issue Title]**
   - Expected: [what plan says]
   - Found: [what codebase has]
   - Impact: [how this affects implementation]
   - Recommendation: [suggested fix]

### Implementation Steps (from plan)
□ 1. [Step description]
□ 2. [Step description]
...

### Ready to Proceed?
[Yes/No with explanation]
```

### Step 5: Create Todo List

If no blocking issues, create todos using TodoWrite:

```
- Phase [N]: [Step 1 description]
- Phase [N]: [Step 2 description]
- Phase [N]: [Step 3 description]
...
- Phase [N]: Update IMPLEMENTATION_PHASES.md
```

### Step 6: Wait for Confirmation

After presenting analysis:

```
Analysis complete. Found [N] issues ([critical/non-critical]).

Ready to begin implementation?
- Type "proceed" to start coding
- Type "fix [issue]" to address specific issue first
- Type "update plan" if plan needs modification
```

## Issue Severity Levels

| Level | Description | Action |
|-------|-------------|--------|
| 🔴 **Critical** | Blocks implementation entirely | Must fix before proceeding |
| 🟡 **Warning** | Can proceed but needs attention | Note and handle during implementation |
| 🟢 **Info** | Minor discrepancy | Proceed, adjust as needed |

## Examples

### Example 1: Clean Start
```
/start_phase 3

## Phase 3: Textract Chunking Pipeline - Analysis Complete

### Prerequisites Check
- ✅ Phase 1 completed (DB schemas created)
- ✅ Phase 2 completed (Chat history working)
- ✅ Required tables exist: rag.messages, rag.chat_documents

### Plan Files Reviewed
1. COMPLETE_CHUNKING_STRATEGY.md - Main guide for TABLE vs TEXT chunks
2. TRANSFORMATION_OF_CELL_GROUNDING.md - Cell ID generation logic
3. TRANSFORMATION_OF_LINE_BLOCKS.md - Line grounding map structure

### Codebase Validation
| Plan Reference | Status | Notes |
|----------------|--------|-------|
| app.py:1270-1520 | ✅ Found | Contains RecursiveCharacterTextSplitter |
| backend/services/ | ✅ Exists | Ready for new files |
| Weaviate DocumentChunk | ✅ Valid | 22 properties configured |

### Issues Found
None - plan aligns with codebase.

### Implementation Steps
□ 1. Create backend/services/textract_parser.py
□ 2. Create backend/services/chunk_transformer.py
□ 3. Generate embeddings with text-embedding-3-large
□ 4. Index in Weaviate with grounding maps
□ 5. Replace app.py lines 1270-1520

Ready to proceed? (yes/no)
```

### Example 2: Issues Found
```
/start_phase 4

## Phase 4: RAG Search & Query - Analysis Complete

### Issues Found

1. 🔴 **Critical: Phase 3 Not Complete**
   - Expected: Textract chunking implemented
   - Found: Still using RecursiveCharacterTextSplitter
   - Impact: RAG search depends on cell_grounding/line_grounding
   - Recommendation: Complete Phase 3 first

2. 🟡 **Warning: Weaviate Schema Missing Properties**
   - Expected: cell_grounding, line_grounding properties
   - Found: Properties not in current schema
   - Impact: Can't store grounding maps for highlighting
   - Recommendation: Update Weaviate schema before Phase 4

Cannot proceed until Phase 3 is completed.
```

## Notes

- Always read plan files FULLY before analyzing
- Check git status for uncommitted changes in target files
- If plan references specific line numbers, verify they're still accurate
- Create detailed todos that can be resumed if session ends
- This command is READ-ONLY - no code changes until user confirms

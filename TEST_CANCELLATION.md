# COA Processing Cancellation Test Plan

## Issue Fixed
RAG indexing background task was not checking for cancellation, causing the process to continue even after the user hit the stop button.

## Changes Made

### 1. Added 6 Cancellation Checkpoints in RAG Indexing (app.py lines 1285-1456)

**Checkpoint locations:**
- Line 1285: At the start of RAG indexing
- Line 1303: After text extraction from blocks.json
- Line 1321: Before generating embeddings
- Line 1329: After embeddings generation
- Line 1352: Before source creation
- Line 1456: Inside chunk upload loop (checks before each chunk)

### 2. Added 2 Cancellation Checkpoints in Final Processing (app.py lines 1530-1539)

**Checkpoint locations:**
- Line 1530: Before final progress simulation (81-100%)
- Line 1539: After final progress simulation completes

### 3. Moved results_store Write to After All Checks (app.py lines 1261-1543)
- Results data prepared early (line 1262) but NOT stored yet
- Results ONLY stored after all cancellation checks pass (line 1543)
- Prevents UI from showing status bar if process was cancelled

### 4. Improved Exception Handling (app.py line 1515-1520)
- Distinguishes between cancellation and real errors
- Logs cancellations as info (not error)
- Avoids printing traceback for cancellations

## How It Works

When user clicks the red stop button:
1. Frontend calls: `POST /cancel-process/{process_id}`
2. Backend sets: `cancellation_tokens[process_id] = True`
3. Background task calls `check_cancellation(process_id)` at each checkpoint
4. If cancelled, raises: `Exception("Process {process_id} cancelled by user")`
5. Exception bubbles up, process stops, files cleaned up
6. Status bar updates to "cancelled" and disappears

## IMPORTANT: Restart Backend Server

**You MUST restart the backend server for these changes to take effect!**

```bash
# Stop the current backend process (Ctrl+C)
cd backend
python app.py
```

## Testing Instructions

### Test Case 1: Cancel During Text Extraction
1. Upload a large COA PDF
2. **Click stop button** immediately after "Found blocks.json, starting Iliad indexing" log appears
3. **Expected:** Process stops, logs show: `[COA-RAG] ⏹️ Indexing stopped for process ... - user cancelled`
4. **Expected:** Status bar disappears from UI
5. **Expected:** No further `[COA-RAG]` logs after cancellation

### Test Case 2: Cancel During Embedding Generation
1. Upload a COA PDF
2. Wait for log: `[COA-RAG] Split into X chunks`
3. **Click stop button** before embeddings complete
4. **Expected:** Process stops during embedding generation
5. **Expected:** Status bar disappears from UI

### Test Case 3: Cancel During Chunk Upload
1. Upload a COA PDF
2. Wait for log: `[COA-RAG] Generated X embeddings`
3. **Click stop button** while chunks are being uploaded
4. **Expected:** Chunk uploads stop (not all chunks uploaded)
5. **Expected:** Log shows: `[COA-RAG] ⏹️ Indexing stopped for process ... - user cancelled`
6. **Expected:** Partial chunks cleaned up

### Test Case 4: Cancel Before RAG Indexing Starts
1. Upload a COA PDF
2. **Click stop button** during Advanced Validation phase (60-80%)
3. **Expected:** Process stops before RAG indexing starts
4. **Expected:** No `[COA-RAG]` logs appear
5. **Expected:** Status bar disappears from UI

### Test Case 5: Full Processing (No Cancellation)
1. Upload a COA PDF
2. Let it complete fully
3. **Expected:** All chunks indexed successfully
4. **Expected:** Log shows: `[COA-RAG] ✅ Successfully indexed X chunks for process: ...`
5. **Expected:** Status bar shows "Download Results" and "Chat with Data" buttons

## Log Markers to Watch For

### Successful Cancellation Logs:
```
🛑 Cancel request received for process: <process_id>
🛑 Process <process_id> marked as cancelled
⏹️ Process <process_id> stopping due to cancellation - cleanup starting
⏹️ Process <process_id> cleanup complete - raising cancellation exception
[COA-RAG] ⏹️ Indexing stopped for process <process_id> - user cancelled
⏹️ Process <process_id> was cancelled by user
```

### Indicators of Issue (if these appear after stop button):
```
[COA-RAG] Chunk X/Y accepted for processing - task_id: ...
[COA-RAG] Uploaded chunk X/Y for process ...
[COA-RAG] ✅ Successfully indexed X chunks for process: ...
```

## Expected Behavior Summary

| Stage | Before Fix | After Fix |
|-------|-----------|-----------|
| **Before RAG** | Stops ✅ | Stops ✅ |
| **During RAG text extraction** | Continues ❌ | Stops ✅ |
| **During embeddings** | Continues ❌ | Stops ✅ |
| **During chunk upload** | Continues ❌ | Stops ✅ |
| **Status bar** | Stays visible ❌ | Disappears ✅ |
| **Background logs** | Keep appearing ❌ | Stop immediately ✅ |

## File Cleanup Behavior (Windows)

On Windows, some files may remain locked by processes (like pandas reading Excel files) even after cancellation. The cleanup function now has **retry logic with garbage collection**:

### Cleanup Process:
1. **Garbage collection** runs to close file handles
2. **3 retry attempts** with 500ms delays for locked files
3. **Graceful handling** - logs warning if file can't be deleted
4. **Auto-overwrite** - locked files will be overwritten on next upload

### Expected Warnings (Normal):
```
⚠️ Failed to cleanup file after 3 attempts (file may be in use): ...textract.xlsx
💡 File will be overwritten on next upload: SAF_HL4689_textract.xlsx
```

**This is expected behavior on Windows and does NOT break functionality.** The file will be automatically overwritten when you upload the same document again.

## Additional Notes

- The fix does NOT affect the main COA processing pipeline (Textract, GPT analysis, Advanced Validation)
- Those stages already had proper cancellation checks
- This fix ONLY adds cancellation to the RAG indexing background task
- No changes to frontend required
- No changes to HBR processing required

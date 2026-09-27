---
date: 2026-03-03T12:00:00+00:00
phase: Performance Optimization
status: in_progress
last_updated: 2026-03-03
---

# Handoff: Frontend Performance Optimization

## Current Status

**Phase:** Performance Optimization
**Progress:** 70% complete (5 of 7 major fixes done)
**Status:** in_progress

## Task Summary

| Task                              | Status     | Notes                                    |
| --------------------------------- | ---------- | ---------------------------------------- |
| Debug Removal                     | ✅ Done    | Removed console.logs, forced delays      |
| Dynamic Imports                   | ✅ Done    | PDFPanel, PDFPanelTest with `ssr: false` |
| React.memo                        | ✅ Done    | PageReferenceButtons, LoadingDots        |
| Backdrop Blur Optimization        | ✅ Done    | Changed xl → sm                          |
| Chat Sidebar Virtualization       | ✅ Done    | TanStack Virtual in ChatSidebar.tsx      |
| Message List Virtualization       | ✅ Done    | TanStack Virtual in page.tsx             |
| useCallback on Event Handlers     | ✅ Done    | Key handlers wrapped                     |
| useMemo on Expensive Computations | ⬜ Pending | Next priority                            |
| Lazy Load Konva                   | ⬜ Pending | ~1.7MB bundle reduction                  |
| Split Monolithic Component        | ⬜ Pending | page.tsx is 4000+ lines                  |

## Files Changed This Session

### Modified Files

| File                                      | Changes | Description                                       |
| ----------------------------------------- | ------- | ------------------------------------------------- |
| `frontend/src/app/chat/page.tsx`          | Major   | Added TanStack Virtual, useCallback, fixed scroll |
| `frontend/src/components/ChatSidebar.tsx` | Major   | Added TanStack Virtual for chat list              |
| `frontend/package.json`                   | Minor   | Added @tanstack/react-virtual dependency          |
| `frontend/src/components/PDFPanel.tsx`    | Minor   | Removed debug elements (earlier)                  |

## Current Work State

### What Was Completed

1. **Message List Virtualization**
   - Removed `flex-col-reverse` layout
   - Implemented TanStack Virtual with `useVirtualizer`
   - Fixed centering with `flex justify-center` wrapper
   - Fixed scroll behavior with direct DOM scroll

2. **Chat Sidebar Virtualization**
   - Flattened grouped chats for virtualization
   - Headers and chat items in single virtual list

3. **Scroll Behavior Fixes**
   - Changed from `scrollToIndex` to direct `scrollTo(scrollHeight)`
   - Added `isAutoScrollingRef` to prevent scroll detection during programmatic scroll
   - Increased scroll threshold from 50px to 100px
   - Used `requestAnimationFrame` for proper timing

### Key Code Locations

```typescript
// Message Virtualizer - page.tsx:858-864
const messageVirtualizer = useVirtualizer({
  count: messages.length,
  getScrollElement: () => chatContainerRef.current,
  estimateSize: () => 120,
  overscan: 5,
});

// Scroll to Bottom - page.tsx:866-880
const scrollChatToBottom = useCallback(
  (behavior: "smooth" | "auto" = "smooth") => {
    if (chatContainerRef.current) {
      isAutoScrollingRef.current = true;
      const container = chatContainerRef.current;
      container.scrollTo({
        top: container.scrollHeight,
        behavior: behavior,
      });
      setTimeout(
        () => {
          isAutoScrollingRef.current = false;
        },
        behavior === "smooth" ? 500 : 100,
      );
    }
  },
  [],
);
```

## Critical Context

### Architecture Decisions Made

1. **Removed flex-col-reverse** - Virtualization doesn't work with reversed flex. Changed to normal scroll direction with `scrollTo(scrollHeight)` for bottom anchoring.

2. **Direct DOM scroll vs virtualizer.scrollToIndex** - `scrollToIndex` was unreliable during dynamic updates. Direct DOM `scrollTo` is more reliable.

3. **Centering with absolute positioning** - Used `flex justify-center` wrapper around absolutely positioned items since `mx-auto` doesn't work with absolute positioning.

### Key Files to Understand

- `frontend/src/app/chat/page.tsx:3385-3640` - Virtualized message rendering
- `frontend/src/app/chat/page.tsx:858-900` - Virtualizer setup and scroll helpers
- `frontend/src/app/chat/page.tsx:1000-1048` - Scroll detection logic
- `frontend/src/components/ChatSidebar.tsx:225-260` - Chat list virtualizer

## Issues Encountered & Solutions

| Issue                                 | Solution                                                 |
| ------------------------------------- | -------------------------------------------------------- |
| Messages moved to left                | Changed `mx-auto` to `flex justify-center` wrapper       |
| Scroll jumping during loading         | Added `isAutoScrollingRef` flag to skip scroll detection |
| New messages not showing              | Changed to direct DOM scroll + requestAnimationFrame     |
| flex-col-reverse broke virtualization | Removed it, use normal scroll + scrollTo(bottom)         |

## Remaining Tasks

### HIGH Priority

1. **useMemo on Expensive Computations**
   - Cache `messages.find(m => m.isStreaming)`
   - Cache `messages.some(m => m.isNew)`
   - Cache filtered/grouped data

### MEDIUM Priority

2. **Lazy Load Konva**

   ```typescript
   const Konva = dynamic(() => import("react-konva"), { ssr: false });
   ```

3. **Split Monolithic Component**
   - Extract MessageItem component
   - Extract ChatInput component
   - Extract ProcessingBlock component

## How to Resume

```bash
# In next Claude Code session:
/resume_handoff frontend/feature_implementation/handoffs/PERFORMANCE_OPTIMIZATION/2026-03-03_performance_virtualization.md
```

Or manually:

1. Read this document
2. Run `cd frontend && npm run dev` to test current state
3. Continue with useMemo implementation

## Verification Commands

```bash
# Check TypeScript compiles
cd frontend && npx tsc --noEmit --skipLibCheck

# Run dev server
cd frontend && npm run dev

# Verify virtualization in browser DevTools:
# - Open Elements tab
# - Search for 'data-index'
# - Should see ~15 elements, not 400+
```

## Performance Metrics (Before → After)

| Metric               | Before | After (Expected) |
| -------------------- | ------ | ---------------- |
| LCP                  | 3.20s  | <2.5s            |
| INP                  | 953ms  | <200ms           |
| DOM Nodes (400 msgs) | 4000+  | ~200             |
| Memory               | ~80MB  | ~20MB            |

---

_Handoff created: 2026-03-03_
_Session duration: ~2 hours_
_Estimated remaining: 1-2 hours for useMemo + Konva_
● Let me check what's remaining from the list you showed:

Performance Fixes Status

✅ COMPLETED

┌─────────────────────────────┬────────────┬───────────────────────────────────┐
│ Fix │ Status │ Impact │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ Debug Removal │ ✅ Done │ Removed logs, delays │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ Dynamic Imports │ ✅ Done │ PDFPanel, PDFPanelTest │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ React.memo │ ✅ Done │ PageReferenceButtons, LoadingDots │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ Backdrop Blur │ ✅ Done │ xl → sm │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ Chat Sidebar Virtualization │ ✅ Done │ TanStack Virtual │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ Message List Virtualization │ ✅ Done │ TanStack Virtual │
├─────────────────────────────┼────────────┼───────────────────────────────────┤
│ useCallback │ ✅ Partial │ Key handlers wrapped │
└─────────────────────────────┴────────────┴───────────────────────────────────┘

❌ REMAINING

┌───────────────────────────────────┬────────┬─────────────────────────────────────────────────┐
│ Fix │ Impact │ Description │
├───────────────────────────────────┼────────┼─────────────────────────────────────────────────┤
│ useMemo on Expensive Computations │ HIGH │ Cache filtered messages, grouped references │
├───────────────────────────────────┼────────┼─────────────────────────────────────────────────┤
│ Lazy Load Konva │ MEDIUM │ Dynamic import for konva + react-konva (~1.7MB) │
├───────────────────────────────────┼────────┼─────────────────────────────────────────────────┤
│ Split Monolithic Component │ MEDIUM │ Break page.tsx into smaller components │
└───────────────────────────────────┴────────┴─────────────────────────────────────────────────┘

---

Next Recommended Fix: useMemo

This will cache expensive computations that run every render:

// Example: Instead of filtering every render
const streamingMessage = messages.find(m => m.isStreaming);

// With useMemo: Only recalculates when messages change
const streamingMessage = useMemo(() =>
messages.find(m => m.isStreaming),
[messages]
);

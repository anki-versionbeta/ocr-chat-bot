# UI/UX Enhancements - Landing AI Style

> **Goal:** Polish the app to look and feel like Landing AI
> **Prerequisite:** Complete BBOX_HIGHLIGHT_IMPLEMENTATION.md first
> **Created:** January 2026

---

## Table of Contents

1. [Current vs Target](#current-vs-target)
2. [Feature List](#feature-list)
3. [Page Thumbnails Sidebar](#page-thumbnails-sidebar)
4. [Zoom and Pan Controls](#zoom-and-pan-controls)
5. [Loading States](#loading-states)
6. [Animations and Transitions](#animations-and-transitions)
7. [Region Badges and Tooltips](#region-badges-and-tooltips)
8. [Color Scheme and Design System](#color-scheme-and-design-system)
9. [Dark Mode](#dark-mode)
10. [Enhanced Chat Panel](#enhanced-chat-panel)
11. [Export Options Panel](#export-options-panel)
12. [Keyboard Shortcuts](#keyboard-shortcuts)
13. [Mobile Responsiveness](#mobile-responsiveness)
14. [Complete Enhanced Layout](#complete-enhanced-layout)

---

## Current vs Target

```
CURRENT (Basic):                         TARGET (Landing AI Style):
┌─────────────┬─────────────┐           ┌───┬─────────────┬─────────────┐
│             │             │           │ T │             │   Modern    │
│   PDF       │   Basic     │           │ H │   PDF       │   Chat UI   │
│   Image     │   Chat      │           │ U │   + Zoom    │   + Refs    │
│             │             │           │ M │   + Pan     │   + Export  │
│  [box]      │             │           │ B │  [badges]   │   Panel     │
│             │             │           │ S │  [tooltips] │             │
├─────────────┤             │           ├───┼─────────────┤             │
│ ◀ Page 2 ▶ │             │           │   │ Zoom + Nav  │             │
└─────────────┴─────────────┘           └───┴─────────────┴─────────────┘
```

---

## Feature List

### Priority 1 (Must Have)
- [ ] Page thumbnails sidebar
- [ ] Zoom controls (+/-, fit to width, fit to page)
- [ ] Loading skeletons
- [ ] Region type badges
- [ ] Smooth highlight animations

### Priority 2 (Should Have)
- [ ] Hover tooltips on regions
- [ ] Better color scheme
- [ ] Enhanced chat UI (typing indicator, timestamps)
- [ ] Export options panel
- [ ] Keyboard shortcuts

### Priority 3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Pan/drag to move around zoomed PDF
- [ ] Multi-select regions
- [ ] Mobile responsive layout
- [ ] Search within document

---

## Page Thumbnails Sidebar

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────┐                                                    │
│  │  1  │  ← Thumbnail (click to navigate)                   │
│  │ ┌─┐ │                                                    │
│  │ └─┘ │                                                    │
│  └─────┘                                                    │
│  ┌─────┐                                                    │
│  │  2  │  ← Active page (highlighted border)                │
│  │ ┌─┐ │     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━                   │
│  │ └─┘ │                                                    │
│  └─────┘                                                    │
│  ┌─────┐                                                    │
│  │  3  │                                                    │
│  │     │                                                    │
│  └─────┘                                                    │
│    ...                                                      │
└─────────────────────────────────────────────────────────────┘
```

### Component

```tsx
// components/ThumbnailSidebar.tsx
import { useState, useEffect } from 'react';

interface Props {
  documentId: string;
  totalPages: number;
  currentPage: number;
  onPageSelect: (page: number) => void;
}

export function ThumbnailSidebar({
  documentId,
  totalPages,
  currentPage,
  onPageSelect
}: Props) {
  const [thumbnails, setThumbnails] = useState<string[]>([]);

  useEffect(() => {
    // Load thumbnail URLs for all pages
    const urls = Array.from({ length: totalPages }, (_, i) =>
      `/api/documents/${documentId}/thumbnails/${i + 1}`
    );
    setThumbnails(urls);
  }, [documentId, totalPages]);

  return (
    <div className="thumbnail-sidebar">
      <div className="thumbnail-header">
        <span className="thumbnail-title">Pages</span>
        <span className="thumbnail-count">{totalPages}</span>
      </div>

      <div className="thumbnail-list">
        {thumbnails.map((url, index) => (
          <div
            key={index}
            className={`thumbnail-item ${currentPage === index + 1 ? 'active' : ''}`}
            onClick={() => onPageSelect(index + 1)}
          >
            <img
              src={url}
              alt={`Page ${index + 1}`}
              loading="lazy"
            />
            <span className="thumbnail-number">{index + 1}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Backend - Generate Thumbnails

```python
# services/thumbnail_service.py
import fitz  # PyMuPDF

def generate_thumbnails(
    pdf_path: str,
    document_id: str,
    output_dir: str = "static/thumbnails",
    width: int = 150
) -> list[str]:
    """Generate small thumbnails for sidebar"""

    doc = fitz.open(pdf_path)
    doc_dir = Path(output_dir) / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    thumbnail_urls = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Calculate zoom to fit width
        zoom = width / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)

        # Save as WebP (smaller file size)
        filename = f"thumb_{page_num + 1}.webp"
        filepath = doc_dir / filename
        pixmap.save(str(filepath))

        thumbnail_urls.append(f"/static/thumbnails/{document_id}/{filename}")

    doc.close()
    return thumbnail_urls
```

### CSS

```css
/* Thumbnail Sidebar */
.thumbnail-sidebar {
  width: 120px;
  background: #f8f9fa;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.thumbnail-header {
  padding: 12px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.thumbnail-title {
  font-weight: 600;
  font-size: 13px;
  color: #333;
}

.thumbnail-count {
  background: #e3f2fd;
  color: #1976d2;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
}

.thumbnail-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.thumbnail-item {
  position: relative;
  margin-bottom: 8px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.thumbnail-item:hover {
  border-color: #90caf9;
}

.thumbnail-item.active {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.3);
}

.thumbnail-item img {
  width: 100%;
  display: block;
}

.thumbnail-number {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
}
```

---

## Zoom and Pan Controls

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  PDF VIEWER TOOLBAR                                         │
│  ┌────┐ ┌────┐ ┌────┐   ┌──────────┐   ┌────┐ ┌────┐       │
│  │ -  │ │100%│ │ +  │   │ Fit Width│   │ ◀  │ │ ▶  │ 2/50  │
│  └────┘ └────┘ └────┘   └──────────┘   └────┘ └────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Component

```tsx
// components/ZoomControls.tsx
import { useState } from 'react';

interface Props {
  zoom: number;
  onZoomChange: (zoom: number) => void;
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

export function ZoomControls({
  zoom,
  onZoomChange,
  currentPage,
  totalPages,
  onPageChange
}: Props) {
  const [showZoomMenu, setShowZoomMenu] = useState(false);

  const zoomIn = () => {
    const nextZoom = ZOOM_LEVELS.find(z => z > zoom) || zoom;
    onZoomChange(nextZoom);
  };

  const zoomOut = () => {
    const prevZoom = [...ZOOM_LEVELS].reverse().find(z => z < zoom) || zoom;
    onZoomChange(prevZoom);
  };

  const fitToWidth = () => {
    onZoomChange(-1); // -1 signals "fit to width"
  };

  const fitToPage = () => {
    onZoomChange(-2); // -2 signals "fit to page"
  };

  return (
    <div className="zoom-controls">
      {/* Zoom Section */}
      <div className="zoom-section">
        <button
          className="zoom-btn"
          onClick={zoomOut}
          disabled={zoom <= ZOOM_LEVELS[0]}
          title="Zoom Out (Ctrl+-)"
        >
          <MinusIcon />
        </button>

        <div className="zoom-dropdown">
          <button
            className="zoom-value"
            onClick={() => setShowZoomMenu(!showZoomMenu)}
          >
            {zoom > 0 ? `${Math.round(zoom * 100)}%` : 'Fit'}
          </button>

          {showZoomMenu && (
            <div className="zoom-menu">
              {ZOOM_LEVELS.map(level => (
                <button
                  key={level}
                  onClick={() => {
                    onZoomChange(level);
                    setShowZoomMenu(false);
                  }}
                  className={zoom === level ? 'active' : ''}
                >
                  {Math.round(level * 100)}%
                </button>
              ))}
              <div className="zoom-divider" />
              <button onClick={fitToWidth}>Fit to Width</button>
              <button onClick={fitToPage}>Fit to Page</button>
            </div>
          )}
        </div>

        <button
          className="zoom-btn"
          onClick={zoomIn}
          disabled={zoom >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1]}
          title="Zoom In (Ctrl++)"
        >
          <PlusIcon />
        </button>
      </div>

      {/* Page Navigation */}
      <div className="page-section">
        <button
          className="nav-btn"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          title="Previous Page (←)"
        >
          <ChevronLeftIcon />
        </button>

        <span className="page-indicator">
          <input
            type="number"
            value={currentPage}
            onChange={(e) => {
              const page = parseInt(e.target.value);
              if (page >= 1 && page <= totalPages) {
                onPageChange(page);
              }
            }}
            min={1}
            max={totalPages}
          />
          <span className="page-separator">/</span>
          <span className="total-pages">{totalPages}</span>
        </span>

        <button
          className="nav-btn"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          title="Next Page (→)"
        >
          <ChevronRightIcon />
        </button>
      </div>
    </div>
  );
}
```

### CSS

```css
/* Zoom Controls */
.zoom-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
  gap: 24px;
}

.zoom-section {
  display: flex;
  align-items: center;
  gap: 4px;
}

.zoom-btn, .nav-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #ddd;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.zoom-btn:hover, .nav-btn:hover {
  background: #f5f5f5;
  border-color: #bbb;
}

.zoom-btn:disabled, .nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.zoom-dropdown {
  position: relative;
}

.zoom-value {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  min-width: 70px;
}

.zoom-menu {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 100;
  min-width: 120px;
  overflow: hidden;
}

.zoom-menu button {
  display: block;
  width: 100%;
  padding: 8px 12px;
  text-align: left;
  border: none;
  background: white;
  cursor: pointer;
  font-size: 13px;
}

.zoom-menu button:hover {
  background: #f5f5f5;
}

.zoom-menu button.active {
  background: #e3f2fd;
  color: #1976d2;
}

.zoom-divider {
  height: 1px;
  background: #e0e0e0;
  margin: 4px 0;
}

/* Page Navigation */
.page-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.page-indicator input {
  width: 40px;
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  text-align: center;
  font-size: 13px;
}

.page-separator {
  color: #999;
}

.total-pages {
  color: #666;
}
```

---

## Loading States

### Skeleton Loaders

```tsx
// components/Skeleton.tsx

export function PageSkeleton() {
  return (
    <div className="skeleton-page">
      <div className="skeleton-image pulse" />
    </div>
  );
}

export function ThumbnailSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="skeleton-thumbnails">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton-thumb pulse" />
      ))}
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="skeleton-chat">
      <div className="skeleton-message user pulse" />
      <div className="skeleton-message assistant pulse" />
      <div className="skeleton-message assistant short pulse" />
    </div>
  );
}

export function RegionSkeleton() {
  return (
    <div className="skeleton-regions">
      <div className="skeleton-region pulse" />
      <div className="skeleton-region pulse" />
      <div className="skeleton-region small pulse" />
    </div>
  );
}
```

### CSS

```css
/* Skeleton Loaders */
.pulse {
  animation: pulse 1.5s ease-in-out infinite;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
}

@keyframes pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-page {
  padding: 20px;
  display: flex;
  justify-content: center;
}

.skeleton-image {
  width: 100%;
  max-width: 800px;
  aspect-ratio: 8.5/11;
  border-radius: 4px;
}

.skeleton-thumbnails {
  padding: 8px;
}

.skeleton-thumb {
  width: 100%;
  aspect-ratio: 8.5/11;
  border-radius: 4px;
  margin-bottom: 8px;
}

.skeleton-message {
  border-radius: 8px;
  margin-bottom: 12px;
}

.skeleton-message.user {
  height: 40px;
  width: 60%;
  margin-left: auto;
}

.skeleton-message.assistant {
  height: 80px;
  width: 80%;
}

.skeleton-message.short {
  height: 40px;
  width: 50%;
}

.skeleton-region {
  height: 60px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.skeleton-region.small {
  height: 40px;
  width: 70%;
}
```

### Typing Indicator

```tsx
// components/TypingIndicator.tsx

export function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <span className="typing-dot"></span>
      <span className="typing-dot"></span>
      <span className="typing-dot"></span>
    </div>
  );
}
```

```css
/* Typing Indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  background: #f5f5f5;
  border-radius: 18px;
  width: fit-content;
}

.typing-dot {
  width: 8px;
  height: 8px;
  background: #999;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-8px); }
}
```

---

## Animations and Transitions

### Highlight Animation

```css
/* Smooth Highlight Animations */

/* Fade in highlight when clicking reference */
.highlight-enter {
  animation: highlightFadeIn 0.3s ease-out;
}

@keyframes highlightFadeIn {
  from {
    opacity: 0;
    transform: scale(1.05);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Pulse effect for active highlight */
.highlight-pulse {
  animation: highlightPulse 2s ease-in-out infinite;
}

@keyframes highlightPulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(255, 193, 7, 0);
  }
}

/* Page transition */
.page-transition {
  animation: pageSlide 0.2s ease-out;
}

@keyframes pageSlide {
  from {
    opacity: 0.5;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* Hover effects */
.region-hover {
  transition: all 0.15s ease;
}

.region-hover:hover {
  filter: brightness(0.95);
}

/* Panel slide */
.panel-slide-in {
  animation: slideIn 0.25s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
```

### React-Konva Animation

```tsx
// components/AnimatedHighlight.tsx
import { Rect } from 'react-konva';
import { useState, useEffect } from 'react';

interface Props {
  x: number;
  y: number;
  width: number;
  height: number;
  isNew?: boolean;
}

export function AnimatedHighlight({ x, y, width, height, isNew }: Props) {
  const [opacity, setOpacity] = useState(isNew ? 0 : 0.35);
  const [scale, setScale] = useState(isNew ? 1.05 : 1);

  useEffect(() => {
    if (isNew) {
      // Animate in
      const timer = setTimeout(() => {
        setOpacity(0.35);
        setScale(1);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isNew]);

  return (
    <Rect
      x={x - (width * (scale - 1)) / 2}
      y={y - (height * (scale - 1)) / 2}
      width={width * scale}
      height={height * scale}
      fill={`rgba(255, 235, 59, ${opacity})`}
      stroke="#FFC107"
      strokeWidth={2}
      cornerRadius={4}
      shadowColor="rgba(255, 193, 7, 0.5)"
      shadowBlur={isNew ? 15 : 0}
      shadowOpacity={0.5}
    />
  );
}
```

---

## Region Badges and Tooltips

### Region Badge Types

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ TABLE                                               │   │
│   │ ┌───────┬───────┬───────┐                          │   │
│   │ │ Col 1 │ Col 2 │ Col 3 │                          │   │
│   │ ├───────┼───────┼───────┤                          │   │
│   │ │ ...   │ ...   │ ...   │                          │   │
│   │ └───────┴───────┴───────┘                          │   │
│   └─────────────────────────────────────────────────────┘   │
│       ↑                                                      │
│    Badge showing region type                                 │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ TEXT                                                │   │
│   │ Lorem ipsum dolor sit amet, consectetur...          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Component

```tsx
// components/RegionBadge.tsx
import { Label, Tag, Text } from 'react-konva';

interface Props {
  x: number;
  y: number;
  type: string;
  section?: string;
}

const TYPE_COLORS: Record<string, string> = {
  table: '#4CAF50',
  text: '#2196F3',
  title: '#9C27B0',
  list: '#FF9800',
  figure: '#E91E63',
  default: '#607D8B'
};

export function RegionBadge({ x, y, type, section }: Props) {
  const color = TYPE_COLORS[type.toLowerCase()] || TYPE_COLORS.default;
  const label = type.toUpperCase();

  return (
    <Label x={x} y={y - 24}>
      <Tag
        fill={color}
        cornerRadius={4}
        shadowColor="rgba(0,0,0,0.2)"
        shadowBlur={4}
        shadowOffsetY={2}
      />
      <Text
        text={label}
        fontSize={10}
        fontStyle="bold"
        fill="white"
        padding={4}
      />
    </Label>
  );
}
```

### Tooltip Component

```tsx
// components/RegionTooltip.tsx
import { useState } from 'react';

interface Props {
  region: {
    type: string;
    section?: string;
    content: string;
    page: number;
  };
  position: { x: number; y: number };
  visible: boolean;
}

export function RegionTooltip({ region, position, visible }: Props) {
  if (!visible) return null;

  return (
    <div
      className="region-tooltip"
      style={{
        left: position.x,
        top: position.y - 10,
        transform: 'translateX(-50%) translateY(-100%)'
      }}
    >
      <div className="tooltip-header">
        <span className={`tooltip-type type-${region.type.toLowerCase()}`}>
          {region.type}
        </span>
        {region.section && (
          <span className="tooltip-section">{region.section}</span>
        )}
      </div>
      <div className="tooltip-content">
        {region.content.slice(0, 100)}
        {region.content.length > 100 && '...'}
      </div>
      <div className="tooltip-footer">
        Page {region.page} • Click to view
      </div>
      <div className="tooltip-arrow" />
    </div>
  );
}
```

### CSS

```css
/* Region Badges */
.region-badge {
  position: absolute;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: white;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  pointer-events: none;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.region-badge.table { background: #4CAF50; }
.region-badge.text { background: #2196F3; }
.region-badge.title { background: #9C27B0; }
.region-badge.list { background: #FF9800; }
.region-badge.figure { background: #E91E63; }

/* Tooltips */
.region-tooltip {
  position: absolute;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  padding: 12px;
  max-width: 300px;
  z-index: 1000;
  pointer-events: none;
  animation: tooltipFadeIn 0.15s ease-out;
}

@keyframes tooltipFadeIn {
  from { opacity: 0; transform: translateX(-50%) translateY(-90%); }
  to { opacity: 1; transform: translateX(-50%) translateY(-100%); }
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.tooltip-type {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: white;
  text-transform: uppercase;
}

.tooltip-type.type-table { background: #4CAF50; }
.tooltip-type.type-text { background: #2196F3; }

.tooltip-section {
  color: #666;
  font-size: 12px;
}

.tooltip-content {
  font-size: 13px;
  color: #333;
  line-height: 1.4;
  margin-bottom: 8px;
}

.tooltip-footer {
  font-size: 11px;
  color: #999;
}

.tooltip-arrow {
  position: absolute;
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 6px solid white;
}
```

---

## Color Scheme and Design System

### CSS Variables

```css
/* Design System - CSS Variables */
:root {
  /* Primary Colors */
  --primary-50: #e3f2fd;
  --primary-100: #bbdefb;
  --primary-200: #90caf9;
  --primary-300: #64b5f6;
  --primary-400: #42a5f5;
  --primary-500: #2196f3;
  --primary-600: #1e88e5;
  --primary-700: #1976d2;
  --primary-800: #1565c0;
  --primary-900: #0d47a1;

  /* Neutral Colors */
  --gray-50: #fafafa;
  --gray-100: #f5f5f5;
  --gray-200: #eeeeee;
  --gray-300: #e0e0e0;
  --gray-400: #bdbdbd;
  --gray-500: #9e9e9e;
  --gray-600: #757575;
  --gray-700: #616161;
  --gray-800: #424242;
  --gray-900: #212121;

  /* Semantic Colors */
  --success: #4caf50;
  --warning: #ff9800;
  --error: #f44336;
  --info: #2196f3;

  /* Highlight Colors */
  --highlight-active: rgba(255, 235, 59, 0.35);
  --highlight-hover: rgba(33, 150, 243, 0.15);
  --highlight-border-active: #ffc107;
  --highlight-border-hover: #2196f3;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  --shadow-xl: 0 20px 25px rgba(0,0,0,0.15);

  /* Border Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* Typography */
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', Monaco, 'Courier New', monospace;

  --text-xs: 11px;
  --text-sm: 13px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 18px;
}
```

### Apply to Components

```css
/* Global Styles */
* {
  box-sizing: border-box;
}

body {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  color: var(--gray-900);
  background: var(--gray-100);
  margin: 0;
  padding: 0;
}

/* Buttons */
.btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
}

.btn-primary {
  background: var(--primary-600);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-700);
}

.btn-secondary {
  background: white;
  color: var(--gray-700);
  border: 1px solid var(--gray-300);
}

.btn-secondary:hover {
  background: var(--gray-50);
  border-color: var(--gray-400);
}

/* Cards */
.card {
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  overflow: hidden;
}

/* Inputs */
.input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--gray-300);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  transition: border-color 0.15s ease;
}

.input:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 3px var(--primary-100);
}
```

---

## Dark Mode

### CSS Variables for Dark Mode

```css
/* Dark Mode Variables */
[data-theme="dark"] {
  --gray-50: #1a1a1a;
  --gray-100: #262626;
  --gray-200: #333333;
  --gray-300: #444444;
  --gray-400: #666666;
  --gray-500: #888888;
  --gray-600: #aaaaaa;
  --gray-700: #cccccc;
  --gray-800: #e0e0e0;
  --gray-900: #f5f5f5;

  --highlight-active: rgba(255, 235, 59, 0.25);
  --highlight-hover: rgba(33, 150, 243, 0.2);
}

[data-theme="dark"] body {
  background: var(--gray-100);
}

[data-theme="dark"] .card {
  background: var(--gray-200);
}

[data-theme="dark"] .input {
  background: var(--gray-200);
  border-color: var(--gray-400);
  color: var(--gray-900);
}
```

### Theme Toggle Component

```tsx
// components/ThemeToggle.tsx
import { useState, useEffect } from 'react';

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    // Check system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme) {
      setIsDark(savedTheme === 'dark');
    } else {
      setIsDark(prefersDark);
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  return (
    <button
      className="theme-toggle"
      onClick={() => setIsDark(!isDark)}
      aria-label="Toggle dark mode"
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
```

```css
/* Theme Toggle */
.theme-toggle {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  border: 1px solid var(--gray-300);
  background: var(--gray-50);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.theme-toggle:hover {
  background: var(--gray-100);
}

.theme-toggle svg {
  width: 20px;
  height: 20px;
  color: var(--gray-600);
}
```

---

## Enhanced Chat Panel

### Modern Chat UI

```tsx
// components/EnhancedChatPanel.tsx
import { useState, useRef, useEffect } from 'react';
import { TypingIndicator } from './TypingIndicator';
import { formatDistanceToNow } from 'date-fns';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  references?: Reference[];
}

export function EnhancedChatPanel({ documentId, onReferenceClick }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="enhanced-chat">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-title">
          <ChatIcon />
          <span>Document Chat</span>
        </div>
        <div className="chat-actions">
          <button className="icon-btn" title="Export chat">
            <ExportIcon />
          </button>
          <button className="icon-btn" title="Clear chat">
            <TrashIcon />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <DocumentSearchIcon />
            <h3>Ask about this document</h3>
            <p>I can help you find information, extract data, or answer questions about the content.</p>

            <div className="suggested-questions">
              <button onClick={() => setInput("What is this document about?")}>
                What is this document about?
              </button>
              <button onClick={() => setInput("Extract all tables to Excel")}>
                Extract all tables to Excel
              </button>
              <button onClick={() => setInput("Summarize the key points")}>
                Summarize the key points
              </button>
            </div>
          </div>
        ) : (
          <>
            {messages.map(msg => (
              <div key={msg.id} className={`message ${msg.role}`}>
                {msg.role === 'assistant' && (
                  <div className="message-avatar">
                    <BotIcon />
                  </div>
                )}

                <div className="message-content">
                  <div className="message-text">{msg.content}</div>

                  {msg.references && msg.references.length > 0 && (
                    <div className="message-references">
                      <span className="ref-label">Sources:</span>
                      {msg.references.map(ref => (
                        <button
                          key={ref.id}
                          className="ref-btn"
                          onClick={() => onReferenceClick(ref.page, ref.bbox)}
                        >
                          <PageIcon />
                          Page {ref.page}
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="message-time">
                    {formatDistanceToNow(msg.timestamp, { addSuffix: true })}
                  </div>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="message assistant">
                <div className="message-avatar">
                  <BotIcon />
                </div>
                <TypingIndicator />
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input-wrapper">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask a question or request an extraction..."
          rows={1}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );
}
```

### CSS

```css
/* Enhanced Chat Panel */
.enhanced-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  border-bottom: 1px solid var(--gray-200);
}

.chat-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  color: var(--gray-800);
}

.chat-actions {
  display: flex;
  gap: var(--space-1);
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--gray-500);
}

.icon-btn:hover {
  background: var(--gray-100);
  color: var(--gray-700);
}

/* Empty State */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
  text-align: center;
}

.chat-empty svg {
  width: 48px;
  height: 48px;
  color: var(--gray-300);
  margin-bottom: var(--space-4);
}

.chat-empty h3 {
  margin: 0 0 var(--space-2);
  color: var(--gray-700);
}

.chat-empty p {
  margin: 0 0 var(--space-6);
  color: var(--gray-500);
  max-width: 280px;
}

.suggested-questions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.suggested-questions button {
  padding: var(--space-3) var(--space-4);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--gray-700);
  transition: all 0.15s ease;
}

.suggested-questions button:hover {
  background: var(--primary-50);
  border-color: var(--primary-200);
  color: var(--primary-700);
}

/* Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
}

.message {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.message.user {
  justify-content: flex-end;
}

.message.user .message-content {
  background: var(--primary-600);
  color: white;
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
  max-width: 80%;
}

.message.assistant .message-content {
  background: var(--gray-100);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm);
  max-width: 85%;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--primary-100);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-avatar svg {
  width: 18px;
  height: 18px;
  color: var(--primary-600);
}

.message-content {
  padding: var(--space-3) var(--space-4);
}

.message-text {
  font-size: var(--text-base);
  line-height: 1.5;
}

.message-time {
  font-size: var(--text-xs);
  color: var(--gray-400);
  margin-top: var(--space-2);
}

.message.user .message-time {
  color: rgba(255,255,255,0.7);
}

/* References */
.message-references {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--gray-200);
}

.ref-label {
  font-size: var(--text-xs);
  color: var(--gray-500);
  width: 100%;
}

.ref-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--primary-600);
  cursor: pointer;
  transition: all 0.15s ease;
}

.ref-btn:hover {
  background: var(--primary-50);
  border-color: var(--primary-200);
}

/* Input */
.chat-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  padding: var(--space-4);
  border-top: 1px solid var(--gray-200);
}

.chat-input-wrapper textarea {
  flex: 1;
  padding: var(--space-3);
  border: 1px solid var(--gray-300);
  border-radius: var(--radius-lg);
  resize: none;
  font-family: inherit;
  font-size: var(--text-base);
  line-height: 1.5;
  max-height: 120px;
}

.chat-input-wrapper textarea:focus {
  outline: none;
  border-color: var(--primary-500);
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--primary-600);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}

.send-btn:hover:not(:disabled) {
  background: var(--primary-700);
}

.send-btn:disabled {
  background: var(--gray-300);
  cursor: not-allowed;
}

.send-btn svg {
  width: 20px;
  height: 20px;
  color: white;
}
```

---

## Export Options Panel

```tsx
// components/ExportPanel.tsx

interface Props {
  onExport: (format: string, options: ExportOptions) => void;
  isExporting: boolean;
}

export function ExportPanel({ onExport, isExporting }: Props) {
  const [format, setFormat] = useState<'excel' | 'csv' | 'json'>('excel');
  const [includeImages, setIncludeImages] = useState(false);
  const [selectedPages, setSelectedPages] = useState<'all' | 'current' | 'custom'>('all');

  return (
    <div className="export-panel">
      <div className="export-header">
        <ExportIcon />
        <span>Export Data</span>
      </div>

      <div className="export-section">
        <label className="export-label">Format</label>
        <div className="export-formats">
          <button
            className={`format-btn ${format === 'excel' ? 'active' : ''}`}
            onClick={() => setFormat('excel')}
          >
            <ExcelIcon />
            Excel
          </button>
          <button
            className={`format-btn ${format === 'csv' ? 'active' : ''}`}
            onClick={() => setFormat('csv')}
          >
            <CsvIcon />
            CSV
          </button>
          <button
            className={`format-btn ${format === 'json' ? 'active' : ''}`}
            onClick={() => setFormat('json')}
          >
            <JsonIcon />
            JSON
          </button>
        </div>
      </div>

      <div className="export-section">
        <label className="export-label">Pages</label>
        <select
          value={selectedPages}
          onChange={(e) => setSelectedPages(e.target.value as any)}
          className="export-select"
        >
          <option value="all">All pages</option>
          <option value="current">Current page only</option>
          <option value="custom">Custom range...</option>
        </select>
      </div>

      <div className="export-section">
        <label className="export-checkbox">
          <input
            type="checkbox"
            checked={includeImages}
            onChange={(e) => setIncludeImages(e.target.checked)}
          />
          <span>Include images/figures</span>
        </label>
      </div>

      <button
        className="export-btn"
        onClick={() => onExport(format, { includeImages, selectedPages })}
        disabled={isExporting}
      >
        {isExporting ? (
          <>
            <Spinner />
            Exporting...
          </>
        ) : (
          <>
            <DownloadIcon />
            Export {format.toUpperCase()}
          </>
        )}
      </button>
    </div>
  );
}
```

---

## Keyboard Shortcuts

```tsx
// hooks/useKeyboardShortcuts.ts
import { useEffect } from 'react';

interface Shortcuts {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onNextPage: () => void;
  onPrevPage: () => void;
  onFitWidth: () => void;
  onSearch: () => void;
}

export function useKeyboardShortcuts({
  onZoomIn,
  onZoomOut,
  onNextPage,
  onPrevPage,
  onFitWidth,
  onSearch
}: Shortcuts) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't trigger if typing in input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Zoom shortcuts
      if ((e.ctrlKey || e.metaKey) && e.key === '=') {
        e.preventDefault();
        onZoomIn();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '-') {
        e.preventDefault();
        onZoomOut();
      }

      // Page navigation
      if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        onNextPage();
      }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        onPrevPage();
      }

      // Fit to width
      if ((e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        onFitWidth();
      }

      // Search
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        onSearch();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onZoomIn, onZoomOut, onNextPage, onPrevPage, onFitWidth, onSearch]);
}
```

### Keyboard Shortcuts Help Modal

```tsx
// components/ShortcutsModal.tsx

export function ShortcutsModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const shortcuts = [
    { keys: ['Ctrl', '+'], action: 'Zoom in' },
    { keys: ['Ctrl', '-'], action: 'Zoom out' },
    { keys: ['Ctrl', '0'], action: 'Fit to width' },
    { keys: ['→'], action: 'Next page' },
    { keys: ['←'], action: 'Previous page' },
    { keys: ['Ctrl', 'F'], action: 'Search document' },
    { keys: ['Esc'], action: 'Close modal / Clear selection' },
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="shortcuts-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Keyboard Shortcuts</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="shortcuts-list">
          {shortcuts.map((shortcut, i) => (
            <div key={i} className="shortcut-item">
              <div className="shortcut-keys">
                {shortcut.keys.map((key, j) => (
                  <span key={j} className="key">{key}</span>
                ))}
              </div>
              <span className="shortcut-action">{shortcut.action}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

---

## Mobile Responsiveness

```css
/* Mobile Responsive Styles */

/* Tablet (< 1024px) */
@media (max-width: 1024px) {
  .app-container {
    flex-direction: column;
  }

  .thumbnail-sidebar {
    display: none; /* Hide on tablet, use page nav instead */
  }

  .right-panel {
    width: 100%;
    height: 40vh;
  }

  .pdf-panel {
    height: 60vh;
  }
}

/* Mobile (< 768px) */
@media (max-width: 768px) {
  .app-container {
    flex-direction: column;
  }

  /* Tab navigation for mobile */
  .mobile-tabs {
    display: flex;
    border-bottom: 1px solid var(--gray-200);
  }

  .mobile-tab {
    flex: 1;
    padding: var(--space-3);
    text-align: center;
    border: none;
    background: transparent;
    font-weight: 500;
    color: var(--gray-500);
  }

  .mobile-tab.active {
    color: var(--primary-600);
    border-bottom: 2px solid var(--primary-600);
  }

  .pdf-panel, .right-panel {
    height: calc(100vh - 100px);
  }

  .pdf-panel.hidden, .right-panel.hidden {
    display: none;
  }

  /* Simplified zoom controls */
  .zoom-section {
    gap: 2px;
  }

  .zoom-dropdown {
    display: none;
  }

  /* Touch-friendly buttons */
  .zoom-btn, .nav-btn {
    width: 44px;
    height: 44px;
  }

  /* Larger touch targets for references */
  .ref-btn {
    padding: var(--space-3) var(--space-4);
    font-size: var(--text-base);
  }
}

/* Small Mobile (< 480px) */
@media (max-width: 480px) {
  .chat-input-wrapper {
    padding: var(--space-2);
  }

  .message-content {
    padding: var(--space-2) var(--space-3);
    max-width: 90%;
  }

  .export-formats {
    flex-direction: column;
  }

  .format-btn {
    width: 100%;
  }
}
```

---

## Complete Enhanced Layout

### Final App Structure

```tsx
// App.tsx - Complete Enhanced Layout
import { useState } from 'react';
import { ThumbnailSidebar } from './components/ThumbnailSidebar';
import { ZoomControls } from './components/ZoomControls';
import { DocumentViewer } from './components/DocumentViewer';
import { EnhancedChatPanel } from './components/EnhancedChatPanel';
import { ExportPanel } from './components/ExportPanel';
import { ThemeToggle } from './components/ThemeToggle';
import { ShortcutsModal } from './components/ShortcutsModal';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';

export function App() {
  const [documentId] = useState('doc_abc123');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showExport, setShowExport] = useState(false);

  // ... other state

  useKeyboardShortcuts({
    onZoomIn: () => setZoom(z => Math.min(z * 1.25, 3)),
    onZoomOut: () => setZoom(z => Math.max(z / 1.25, 0.5)),
    onNextPage: () => setCurrentPage(p => Math.min(p + 1, totalPages)),
    onPrevPage: () => setCurrentPage(p => Math.max(p - 1, 1)),
    onFitWidth: () => setZoom(-1),
    onSearch: () => {/* open search */}
  });

  return (
    <div className="app-container">
      {/* Left: Thumbnails */}
      <ThumbnailSidebar
        documentId={documentId}
        totalPages={totalPages}
        currentPage={currentPage}
        onPageSelect={setCurrentPage}
      />

      {/* Center: PDF Viewer */}
      <div className="pdf-panel">
        <ZoomControls
          zoom={zoom}
          onZoomChange={setZoom}
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={setCurrentPage}
        />

        <DocumentViewer
          documentId={documentId}
          currentPage={currentPage}
          zoom={zoom}
          // ... other props
        />
      </div>

      {/* Right: Chat + Export */}
      <div className="right-panel">
        <div className="panel-header">
          <ThemeToggle />
          <button
            className="icon-btn"
            onClick={() => setShowExport(!showExport)}
          >
            <ExportIcon />
          </button>
          <button
            className="icon-btn"
            onClick={() => setShowShortcuts(true)}
          >
            <KeyboardIcon />
          </button>
        </div>

        {showExport ? (
          <ExportPanel
            onExport={handleExport}
            isExporting={isExporting}
          />
        ) : (
          <EnhancedChatPanel
            documentId={documentId}
            onReferenceClick={handleReferenceClick}
          />
        )}
      </div>

      {/* Modals */}
      <ShortcutsModal
        isOpen={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </div>
  );
}
```

---

## Implementation Checklist

```
PRIORITY 1 (Must Have):
[ ] Page thumbnails sidebar
[ ] Zoom controls (+/-, fit width, dropdown)
[ ] Loading skeletons (page, thumbnails, chat)
[ ] Region type badges
[ ] Smooth highlight animations
[ ] Typing indicator

PRIORITY 2 (Should Have):
[ ] Hover tooltips on regions
[ ] CSS design system (variables)
[ ] Enhanced chat UI (empty state, timestamps)
[ ] Export options panel
[ ] Keyboard shortcuts

PRIORITY 3 (Nice to Have):
[ ] Dark mode toggle
[ ] Pan/drag on zoomed PDF
[ ] Mobile responsive layout
[ ] Shortcuts help modal
[ ] Search within document
```

---

## Summary

| Feature | Complexity | Impact |
|---------|-----------|--------|
| Thumbnails | Medium | High |
| Zoom Controls | Low | High |
| Loading States | Low | Medium |
| Animations | Low | Medium |
| Badges/Tooltips | Medium | Medium |
| Design System | Low | High |
| Dark Mode | Low | Low |
| Chat UI | Medium | High |
| Export Panel | Medium | Medium |
| Keyboard Shortcuts | Low | Low |
| Mobile Responsive | High | Medium |

**Total Estimated Effort:** 3-5 days for Priority 1 + 2

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Prerequisite: BBOX_HIGHLIGHT_IMPLEMENTATION.md*

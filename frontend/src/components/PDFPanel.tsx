"use client";

/**
 * PDFPanel Component - Phase 5 PDF Viewer with Bbox Highlighting
 *
 * A resizable split-panel that displays PDF with native rendering and bbox highlighting.
 * Uses react-pdf for professional PDF viewing with HTML overlay highlights.
 *
 * Features:
 * - Native PDF rendering (text selection, sharp zoom)
 * - HTML div overlays for bbox highlighting
 * - Resizable split-pane layout with draggable divider
 * - Page navigation with keyboard support
 * - Highlight pulse animation
 * - Responsive design
 *
 * Created: February 2026
 */

import React, { useState, useEffect, useRef, useCallback, useMemo, memo } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Configure PDF.js worker - use local copy for faster loading (no CDN latency)
// Copy pdf.worker.min.js to public folder: cp node_modules/pdfjs-dist/build/pdf.worker.min.js public/
pdfjs.GlobalWorkerOptions.workerSrc = `/pdf.worker.min.js`;

// Types
export interface BoundingBox {
  left: number;
  top: number;
  width: number;
  height: number;
  right?: number;
  bottom?: number;
}

export interface PDFHighlight {
  page: number;
  bbox: BoundingBox;
  text?: string;
  type?: "cell" | "line" | "table_layout";
  highlight_type?: "error" | "info";
}

interface PDFPanelProps {
  processId: string;
  documentName?: string;
  isOpen: boolean;
  onClose: () => void;
  highlights?: PDFHighlight[];
  initialPage?: number;
  pdfUrl?: string;
  onWidthChange?: (width: number) => void; // Callback when panel width changes
  scanningPages?: number[];  // Pages being scanned by Visual Audit
  scanningStage?: 'searching' | 'analyzing' | 'extracting' | 'verifying' | 'complete';  // Visual Audit stage
}

// Global keyframes for scanning animation - defined once outside component
// Added highlightAppear for one-time highlight animation (replaces infinite animate-pulse)
const SCAN_KEYFRAMES = `
  @keyframes scanLineMove {
    0% { top: 0%; }
    50% { top: calc(100% - 4px); }
    100% { top: 0%; }
  }
  @keyframes cornerPulse {
    0%, 100% { opacity: 0.6; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.2); }
  }
  @keyframes dotGlow {
    0% { opacity: 0; transform: scale(0.3); }
    50% { opacity: 1; transform: scale(1); }
    100% { opacity: 0; transform: scale(0.3); }
  }
  @keyframes gridSweep {
    0% { background-position: 0% 0%; }
    100% { background-position: 100% 100%; }
  }
  @keyframes highlightAppear {
    0% { opacity: 0; transform: scale(0.95); }
    50% { opacity: 1; transform: scale(1.02); box-shadow: 0 0 20px rgba(249, 115, 22, 0.9); }
    100% { opacity: 1; transform: scale(1); box-shadow: 0 0 12px rgba(249, 115, 22, 0.7); }
  }
  @keyframes errorLabelPulse {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 6px rgba(220, 38, 38, 0.8); }
    50% { opacity: 0.7; transform: scale(1.05); box-shadow: 0 0 12px rgba(220, 38, 38, 1); }
  }
`;

// Inject keyframes once into document head - use versioned ID to force update
if (typeof document !== 'undefined') {
  const styleId = 'scan-animation-keyframes-v2';
  // Remove old version if exists
  const oldStyle = document.getElementById('scan-animation-keyframes');
  if (oldStyle) oldStyle.remove();

  if (!document.getElementById(styleId)) {
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = SCAN_KEYFRAMES;
    document.head.appendChild(style);
  }
}

// Optimized scanning overlay - reduced dots from 15 to 6 for better performance
// GPU-accelerated with will-change and transform hints
const OPTIMIZED_DOTS = [
  { left: '15%', top: '20%', delay: '0s', duration: '2s' },
  { left: '75%', top: '25%', delay: '0.5s', duration: '2.2s' },
  { left: '40%', top: '50%', delay: '1s', duration: '1.8s' },
  { left: '60%', top: '70%', delay: '0.3s', duration: '2.1s' },
  { left: '25%', top: '75%', delay: '0.8s', duration: '1.9s' },
  { left: '85%', top: '55%', delay: '1.2s', duration: '2s' },
];

const ScanningOverlay = memo(function ScanningOverlay({
  stage,
  pages,
}: {
  stage: string;
  pages: number[];
}) {
  return (
    <div
      className="absolute pointer-events-none"
      style={{
        zIndex: 9999,
        inset: 0,
        isolation: 'isolate',
        willChange: 'transform',  // GPU hint for container
        transform: 'translateZ(0)',  // Force GPU layer
      }}
    >
      {/* Persistent cyan mask overlay with subtle grid pattern */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(34, 211, 238, 0.12)',
          backgroundImage: `
            linear-gradient(rgba(34, 211, 238, 0.08) 1px, transparent 1px),
            linear-gradient(90deg, rgba(34, 211, 238, 0.08) 1px, transparent 1px)
          `,
          backgroundSize: '20px 20px',
          zIndex: 1,
        }}
      />

      {/* Scanning line - GPU accelerated with transform instead of top */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: '100%',
          height: '4px',
          zIndex: 2,
          animation: 'scanLineMove 2s linear infinite',
          background: 'linear-gradient(90deg, transparent 0%, rgba(34, 211, 238, 0.4) 15%, #22d3ee 50%, rgba(34, 211, 238, 0.4) 85%, transparent 100%)',
          boxShadow: '0 0 10px 3px rgba(34, 211, 238, 0.5)',  // Reduced shadow blur
          willChange: 'transform',
        }}
      />

      {/* Optimized glowing dots - reduced from 15 to 6, lighter shadows */}
      {OPTIMIZED_DOTS.map((dot, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            width: 8,  // Slightly smaller
            height: 8,
            borderRadius: '50%',
            backgroundColor: '#22d3ee',
            boxShadow: '0 0 8px 2px rgba(34, 211, 238, 0.6)',  // Reduced shadow
            left: dot.left,
            top: dot.top,
            zIndex: 3,
            animation: `dotGlow ${dot.duration} ease-in-out infinite`,
            animationDelay: dot.delay,
            willChange: 'opacity, transform',  // GPU hint
          }}
        />
      ))}

      {/* Stage indicator with animated dots */}
      <div
        className="flex items-center gap-2 bg-cyan-500/95 text-white px-4 py-2 rounded-full text-xs font-medium shadow-lg backdrop-blur-sm"
        style={{ position: 'absolute', top: 12, left: 12, zIndex: 5 }}
      >
        <div className="flex gap-1">
          <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="ml-1">
          {stage === 'searching' && 'Searching document...'}
          {stage === 'analyzing' && 'Analyzing content...'}
          {stage === 'extracting' && 'Extracting data...'}
          {stage === 'verifying' && 'Verifying results...'}
        </span>
      </div>

      {/* Pages being scanned indicator */}
      <div
        className="bg-black/70 text-white px-3 py-1.5 rounded-full text-xs font-medium backdrop-blur-sm flex items-center gap-2"
        style={{ position: 'absolute', bottom: 12, left: 12, zIndex: 5 }}
      >
        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Scanning page{pages.length > 1 ? 's' : ''}: {pages.join(', ')}</span>
      </div>
    </div>
  );
});

// Backend API URL
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com";

export default function PDFPanel({
  processId,
  documentName = "Document",
  isOpen,
  onClose,
  highlights = [],
  initialPage = 1,
  pdfUrl: propPdfUrl,
  onWidthChange,
  scanningPages = [],
  scanningStage
}: PDFPanelProps) {
  // State
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [totalPages, setTotalPages] = useState(0);
  const [pdfUrl, setPdfUrl] = useState<string | null>(propPdfUrl || null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [pageHeight, setPageHeight] = useState(0);
  const [showHighlights, setShowHighlights] = useState(true);
  const [scale, setScale] = useState(1);
  const [panelWidth, setPanelWidth] = useState(50); // Panel width in vw (50% default)
  const [isDragging, setIsDragging] = useState(false);
  const [rotation, setRotation] = useState(0); // Rotation in degrees (0, 90, 180, 270)
  const [pdfInternalRotation, setPdfInternalRotation] = useState(0); // PDF's built-in rotation

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const pageContainerRef = useRef<HTMLDivElement>(null);
  const dividerRef = useRef<HTMLDivElement>(null);

  // Get highlights for current page
  const currentHighlights = highlights.filter(h => h.page === currentPage);

  // Visual Audit scanning mode - check if actively scanning
  const isScanning = scanningPages.length > 0 && scanningStage && scanningStage !== 'complete';


  // During scanning, restrict navigation to only scanning pages
  const allowedPages = isScanning ? scanningPages : null;

  // Sanitize filename the same way backend does
  const sanitizeFilename = (filename: string): string => {
    // Remove .pdf extension first
    let name = filename.replace(/\.pdf$/i, '');
    // Replace spaces with underscores
    name = name.replace(/\s+/g, '_');
    // Remove parentheses
    name = name.replace(/[()]/g, '');
    // Replace other special chars with underscore
    name = name.replace(/[^a-zA-Z0-9_\-]/g, '_');
    // Clean up multiple underscores
    name = name.replace(/_+/g, '_');
    // Remove trailing underscores
    name = name.replace(/_+$/, '');
    return name;
  };

  // Load PDF URL - construct from document name
  // Keep isLoading=true until PDF actually loads via onDocumentLoadSuccess
  useEffect(() => {
    if (isOpen && !propPdfUrl) {
      if (documentName && documentName !== "Document") {
        // Sanitize filename to match backend naming convention
        const sanitizedName = sanitizeFilename(documentName);
        const url = `${API_BASE}/temp/${encodeURIComponent(sanitizedName)}.pdf`;
        setPdfUrl(url);
        setIsLoading(true);  // Keep loading until PDF renders
        setError(null);
      } else {
        setError("No document name provided. Please upload a document first.");
        setIsLoading(false);
      }
    } else if (propPdfUrl) {
      setPdfUrl(propPdfUrl);
      setIsLoading(true);  // Keep loading until PDF renders
    }
  }, [isOpen, documentName, propPdfUrl, processId]);

  // Update page when initialPage changes OR when highlights change (source click)
  // This ensures clicking a source reference always navigates to that page,
  // even if the user manually changed the page before
  useEffect(() => {
    if (initialPage > 0) {
      setCurrentPage(initialPage);
    }
  }, [initialPage, highlights]);

  // Show highlights when they change (no auto-hide - stays until panel closes)
  useEffect(() => {
    if (highlights.length > 0) {
      setShowHighlights(true);
    }
  }, [highlights]);

  // Reset highlights when panel closes
  useEffect(() => {
    if (!isOpen) {
      setShowHighlights(false);
    }
  }, [isOpen]);

  // Calculate scale based on container width - higher scale for sharper rendering
  useEffect(() => {
    if (containerRef.current && isOpen) {
      const containerWidth = containerRef.current.offsetWidth - 32;
      // Use scale that fits the panel width while maintaining sharpness
      const newScale = Math.min(containerWidth / 612, 1.8);
      setScale(newScale);
    }
  }, [isOpen, panelWidth]);

  // Handle divider drag for resizing
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = (e.clientX / window.innerWidth) * 100;
      // Clamp between 25% and 65% (increased max for rotated/landscape documents)
      const clampedWidth = Math.max(25, Math.min(65, newWidth));
      setPanelWidth(clampedWidth);
      onWidthChange?.(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, onWidthChange]);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setTotalPages(numPages);
    setIsLoading(false);
    setError(null);
  }

  function onDocumentLoadError(err: Error) {
    console.error("PDF load error:", err);
    setError("Failed to load PDF document");
    setIsLoading(false);
  }

  function onPageLoadSuccess(page: { width: number; height: number; rotate?: number }) {
    // Capture PDF's internal rotation
    const internalRotation = (page as any).rotate || 0;
    setPdfInternalRotation(internalRotation);

    // Get actual rendered canvas dimensions after a short delay to ensure DOM is ready
    updateCanvasDimensions();
  }

  // Update canvas dimensions using ResizeObserver for better performance
  // No more setTimeout delays - immediate updates when canvas is ready
  const updateCanvasDimensions = useCallback(() => {
    if (pageContainerRef.current) {
      const canvas = pageContainerRef.current.querySelector('canvas');
      if (canvas) {
        setPageWidth(canvas.offsetWidth);
        setPageHeight(canvas.offsetHeight);
      }
    }
  }, []);

  // Use ResizeObserver for efficient dimension tracking (replaces setTimeout polling)
  useEffect(() => {
    if (!isOpen || !pageContainerRef.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      const container = entries[0]?.target;
      if (container) {
        const canvas = container.querySelector('canvas');
        if (canvas) {
          setPageWidth(canvas.offsetWidth);
          setPageHeight(canvas.offsetHeight);
        }
      }
    });

    resizeObserver.observe(pageContainerRef.current);

    // Initial update after a micro-task to ensure canvas is rendered
    requestAnimationFrame(updateCanvasDimensions);

    return () => resizeObserver.disconnect();
  }, [isOpen, updateCanvasDimensions]);

  // Recalculate dimensions when rotation changes
  useEffect(() => {
    if (isOpen && !isLoading) {
      // Use requestAnimationFrame for smoother updates
      requestAnimationFrame(updateCanvasDimensions);
    }
  }, [rotation, isOpen, isLoading, updateCanvasDimensions]);

  const goToPage = useCallback((page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  }, [totalPages]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      // Skip keyboard shortcuts if user is typing in an input/textarea
      const activeElement = document.activeElement;
      const isTyping = activeElement?.tagName === 'INPUT' ||
                       activeElement?.tagName === 'TEXTAREA' ||
                       (activeElement as HTMLElement)?.isContentEditable;

      if (isTyping) return;

      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        goToPage(currentPage - 1);
      } else if (e.key === "ArrowRight" || e.key === "PageDown") {
        e.preventDefault();
        goToPage(currentPage + 1);
      } else if (e.key === "Escape") {
        onClose();
      }
      // Removed "r" key shortcut - rotation only via button to avoid conflict with typing
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, currentPage, goToPage, onClose]);

  // Transform bounding box coordinates based on rotation
  // Bounding boxes from backend are always in original (0°) orientation
  // We need to transform them to match the rotated view
  function transformBboxForRotation(bbox: BoundingBox, rotationDeg: number): BoundingBox {
    const { left, top, width, height } = bbox;
    const w = width ?? (bbox.right !== undefined ? bbox.right - left : 0);
    const h = height ?? (bbox.bottom !== undefined ? bbox.bottom - top : 0);

    switch (rotationDeg) {
      case 90:
        // 90° clockwise: (x, y) -> (1-y-h, x)
        return {
          left: 1 - top - h,
          top: left,
          width: h,
          height: w,
        };
      case 180:
        // 180°: (x, y) -> (1-x-w, 1-y-h)
        return {
          left: 1 - left - w,
          top: 1 - top - h,
          width: w,
          height: h,
        };
      case 270:
        // 270° clockwise (90° counter-clockwise): (x, y) -> (y, 1-x-w)
        return {
          left: top,
          top: 1 - left - w,
          width: h,
          height: w,
        };
      default:
        // 0° - no transformation
        return { left, top, width: w, height: h };
    }
  }

  // Rotate handler
  const handleRotate = useCallback(() => {
    setRotation((prev) => (prev + 90) % 360);
  }, []);

  function getHighlightStyle(bbox: BoundingBox, highlightType?: string, logIndex?: number): React.CSSProperties {
    // Get raw bbox values from Textract
    const rawLeft = bbox.left ?? 0;
    const rawTop = bbox.top ?? 0;
    const rawWidth = bbox.width ?? (bbox.right !== undefined ? bbox.right - rawLeft : 0);
    const rawHeight = bbox.height ?? (bbox.bottom !== undefined ? bbox.bottom - rawTop : 0);

    // Start with raw values
    let left = rawLeft;
    let top = rawTop;
    let width = rawWidth;
    let height = rawHeight;

    // DIAGNOSTIC LOGGING REMOVED FOR PERFORMANCE
    // Uncomment below for debugging bbox issues:
    // if (logIndex === 0) { console.log('[BBOX]', { pdfInternalRotation, rotation, pageWidth, pageHeight }); }

    // ============================================================
    // TRANSFORMATION LOGIC
    // ============================================================
    // At rotation=0: No transformation (PDF.js handles internal rotation naturally)
    // At rotation>0: Transform bbox to match user's rotation

    // Apply user's manual rotation (rotate button) ONLY
    if (rotation !== 0) {
      const rotated = transformBboxForRotation({ left, top, width, height }, rotation);
      left = rotated.left;
      top = rotated.top;
      width = rotated.width ?? width;
      height = rotated.height ?? height;
    }

    // FINAL POSITION LOGGING REMOVED FOR PERFORMANCE
    // Uncomment for debugging: if (logIndex === 0) { console.log('[BBOX] Final:', { left, top, width, height }); }

    // For very thin highlights (text lines), ensure minimum visibility
    const isTextLine = height < 0.02 && width > height * 3;
    const minHeight = isTextLine ? 0.025 : height;
    const topAdjust = isTextLine ? top - (minHeight - height) / 2 : top;

    // Color based on highlight_type
    const isError = highlightType === 'error';
    const bgColor = isError ? "rgba(239, 68, 68, 0.25)" : "rgba(249, 115, 22, 0.18)";
    const borderColor = isError ? "#dc2626" : "#ea580c";
    const shadowColor = isError ? "rgba(239, 68, 68, 0.9)" : "rgba(249, 115, 22, 0.8)";

    return {
      position: "absolute",
      left: `${left * 100}%`,
      top: `${Math.max(0, topAdjust) * 100}%`,
      width: `${width * 100}%`,
      height: `${minHeight * 100}%`,
      backgroundColor: bgColor,
      border: `3px solid ${borderColor}`,
      borderRadius: "4px",
      boxShadow: `0 0 16px ${shadowColor}`,
      pointerEvents: "none" as const,
      zIndex: 10,
    };
  }

  if (!isOpen) return null;

  return (
    <>
      {/* Split-panel layout: PDF on left, chat remains visible on right */}
      <div
        ref={containerRef}
        className="fixed left-0 top-0 h-screen bg-white shadow-xl z-40 flex flex-col"
        style={{ width: `${panelWidth}vw` }}
      >
        {/* Draggable divider on right edge */}
        <div
          ref={dividerRef}
          onMouseDown={handleMouseDown}
          className={`absolute right-0 top-0 h-full w-1.5 cursor-col-resize z-50
            transition-colors duration-150
            ${isDragging ? 'bg-cyan-500' : 'bg-gray-300 hover:bg-cyan-400'}`}
          style={{ touchAction: 'none' }}
        >
          {/* Divider grip indicator */}
          <div className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 flex flex-col gap-1">
            <div className={`w-1 h-1 rounded-full ${isDragging ? 'bg-white' : 'bg-gray-500'}`} />
            <div className={`w-1 h-1 rounded-full ${isDragging ? 'bg-white' : 'bg-gray-500'}`} />
            <div className={`w-1 h-1 rounded-full ${isDragging ? 'bg-white' : 'bg-gray-500'}`} />
          </div>
        </div>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-slate-50 to-white flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center flex-shrink-0 shadow-md">
              <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM9 13h6v2H9v-2zm0 4h6v2H9v-2z"/>
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-gray-800 truncate">{documentName}</h3>
              <p className="text-xs text-gray-500">{totalPages > 0 ? `${totalPages} pages` : "Loading..."}</p>
            </div>
          </div>

          {currentHighlights.length > 0 && showHighlights && (
            <div className="flex items-center gap-2 mr-3 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-full">
              <div className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
              <span className="text-xs font-medium text-amber-700">
                {currentHighlights.length} highlight{currentHighlights.length > 1 ? "s" : ""}
              </span>
            </div>
          )}

          {/* Rotate button */}
          <button
            onClick={handleRotate}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors group mr-1"
            title={`Rotate 90° (Current: ${rotation}°)`}
          >
            <svg
              className="w-5 h-5 text-gray-500 group-hover:text-cyan-600 transition-transform duration-200"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              style={{ transform: `rotate(${rotation}deg)` }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors group ml-1"
            title="Close (Esc)"
          >
            <svg className="w-5 h-5 text-gray-500 group-hover:text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto bg-gray-100 flex justify-center py-4">
          {isLoading && (
            <div className="flex flex-col items-center justify-center h-full w-full relative">
              {/* Show scanner animation during loading if Visual Audit is active */}
              {/* Simple loading indicator - scanner overlay is rendered separately below */}
              <div className="bg-black/70 backdrop-blur-sm rounded-lg px-4 py-2.5 flex items-center gap-3 z-50">
                <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                <p className="text-white text-sm font-medium">Loading document...</p>
              </div>
            </div>
          )}

          {error && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full w-full">
              <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-red-600 font-medium mb-2">Failed to load PDF</p>
              <p className="text-xs text-gray-500 mb-4">{error}</p>
              <button onClick={onClose} className="px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 text-sm font-medium">
                Close
              </button>
            </div>
          )}

          {pdfUrl && !error && (
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={null}
              className="flex justify-center"
            >
              <div ref={pageContainerRef} className="relative bg-white shadow-xl rounded-lg">
                <Page
                  pageNumber={currentPage}
                  scale={scale}
                  rotate={rotation > 0 ? (pdfInternalRotation + rotation) % 360 : undefined}
                  onLoadSuccess={onPageLoadSuccess}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                />

                {/* Highlight overlay - uses exact canvas pixel dimensions for accurate positioning */}
                {showHighlights && currentHighlights.length > 0 && pageWidth > 0 && pageHeight > 0 && (
                  <div
                    className="absolute pointer-events-none"
                    style={{
                      zIndex: 20,
                      top: 0,
                      left: 0,
                      width: pageWidth,
                      height: pageHeight,
                      boxSizing: 'border-box',
                    }}
                  >

                    {currentHighlights.map((highlight, index) => {
                      const isError = highlight.highlight_type === 'error';
                      const style = getHighlightStyle(highlight.bbox, highlight.highlight_type, index);

                      // Error label uses same position as highlight box (from style)
                      // Extract left and top from the computed style
                      const highlightLeft = style.left as string; // e.g., "75.12%"
                      const highlightTop = parseFloat((style.top as string).replace('%', '')); // get numeric value

                      return (
                        <React.Fragment key={`highlight-${currentPage}-${index}`}>
                          {/* Error label above highlight - positioned relative to highlight box */}
                          {isError && (
                            <div
                              style={{
                                position: "absolute",
                                left: highlightLeft,
                                top: `${Math.max(0, highlightTop - 2.5)}%`,
                                backgroundColor: "#dc2626",
                                color: "white",
                                fontSize: "9px",
                                fontWeight: 600,
                                padding: "2px 6px",
                                borderRadius: "3px",
                                zIndex: 21,
                                boxShadow: "0 0 6px rgba(220, 38, 38, 0.8)",
                                animation: "errorLabelPulse 2s ease-in-out infinite",
                              }}
                            >
                              Error
                            </div>
                          )}
                          <div style={style} className="animate-pulse" />
                        </React.Fragment>
                      );
                    })}
                  </div>
                )}

              </div>
            </Document>
          )}
        </div>

        {/* Footer - During scanning, show only scanning pages navigation */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-white flex-shrink-0">
          {isScanning ? (
            // Scanning mode: Show page selector for scanning pages only
            <>
              <div className="flex items-center gap-2 text-cyan-600">
                <div className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse" />
                <span className="text-sm font-medium">Visual Audit</span>
              </div>
              <div className="flex items-center gap-2">
                {scanningPages.map((page, idx) => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      currentPage === page
                        ? 'bg-cyan-500 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-cyan-100'
                    }`}
                  >
                    Page {page}
                  </button>
                ))}
              </div>
              <div className="text-xs text-gray-400">
                {scanningPages.length} page{scanningPages.length > 1 ? 's' : ''}
              </div>
            </>
          ) : (
            // Normal mode: Full page navigation
            <>
              <button
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage <= 1}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  currentPage <= 1 ? "text-gray-300 cursor-not-allowed" : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span className="hidden sm:inline">Previous</span>
              </button>

              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500">Page</span>
                <input
                  type="number"
                  min={1}
                  max={totalPages}
                  value={currentPage}
                  onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
                  className="w-14 px-2 py-1.5 text-center text-sm font-medium border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-400"
                />
                <span className="text-sm text-gray-500">of {totalPages || "?"}</span>
              </div>

              <button
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  currentPage >= totalPages ? "text-gray-300 cursor-not-allowed" : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <span className="hidden sm:inline">Next</span>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </>
          )}
        </div>

        {/* Visual Audit Scanning Overlay - FIXED position to cover content area without scrolling */}
        {isScanning && (
          <div
            className="pointer-events-none"
            style={{
              position: 'fixed',
              left: 0,
              top: '64px',  // Below header (~64px)
              width: `${panelWidth}vw`,
              bottom: '56px',  // Above footer (~56px)
              zIndex: 9999,
            }}
          >
            <ScanningOverlay
              stage={scanningStage || 'searching'}
              pages={scanningPages}
            />
          </div>
        )}
      </div>
    </>
  );
}

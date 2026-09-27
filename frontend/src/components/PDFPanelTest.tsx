"use client";

/**
 * PDFPanelTest - Isolated test component for bbox positioning
 *
 * Uses hardcoded Textract bounding boxes to test highlight positioning
 * without depending on API data. Once positioning works here,
 * we can copy the logic to the main PDFPanel.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = `/pdf.worker.min.js`;

// Types
interface BoundingBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface TestHighlight {
  bbox: BoundingBox;
  text: string;
  type: "error" | "info";
}

// ============================================================
// HARDCODED TEST DATA FROM TEXTRACT (Actual values from testing_one_blocks.json)
// ============================================================
const TEST_HIGHLIGHTS: TestHighlight[] = [
  {
    // "CERTIFICATE OF ANALYSIS" - should appear TOP-LEFT area
    bbox: {
      left: 0.10765150189399719,
      top: 0.04927792772650719,
      width: 0.3044801354408264,
      height: 0.01260438933968544,
    },
    text: "CERTIFICATE OF ANALYSIS",
    type: "info",
  },
  {
    // "August Faller GmbH & Co. KG" - should appear TOP-RIGHT area
    bbox: {
      left: 0.7512266635894775,
      top: 0.09554387629032135,
      width: 0.1529676765203476,
      height: 0.008007739670574665,
    },
    text: "August Faller GmbH & Co. KG",
    type: "error", // Mark as error to test error label
  },
  {
    // "17,000 PC" - should appear in MIDDLE-RIGHT area
    bbox: {
      left: 0.60182785987854,
      top: 0.17530938982963562,
      width: 0.06999488174915314,
      height: 0.008663160726428032,
    },
    text: "17,000 PC",
    type: "info",
  },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface PDFPanelTestProps {
  pdfUrl: string;
  documentName?: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function PDFPanelTest({
  pdfUrl,
  documentName = "Test Document",
  isOpen,
  onClose,
}: PDFPanelTestProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [pageHeight, setPageHeight] = useState(0);
  const [scale, setScale] = useState(1);
  const [pdfInternalRotation, setPdfInternalRotation] = useState(0);
  const [panelWidth, setPanelWidth] = useState(50);

  const containerRef = useRef<HTMLDivElement>(null);
  const pageContainerRef = useRef<HTMLDivElement>(null);

  // Calculate scale
  useEffect(() => {
    if (containerRef.current && isOpen) {
      const containerWidth = containerRef.current.offsetWidth - 32;
      const newScale = Math.min(containerWidth / 612, 1.8);
      setScale(newScale);
    }
  }, [isOpen, panelWidth]);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setTotalPages(numPages);
    setIsLoading(false);
  }

  function onDocumentLoadError(err: Error) {
    console.error("PDF load error:", err);
    setError("Failed to load PDF");
    setIsLoading(false);
  }

  function onPageLoadSuccess(page: { width: number; height: number; rotate?: number }) {
    const internalRotation = (page as any).rotate || 0;
    setPdfInternalRotation(internalRotation);
    console.log(`[TEST] Page loaded - Internal rotation: ${internalRotation}°`);
    updateCanvasDimensions();
  }

  const updateCanvasDimensions = useCallback(() => {
    if (pageContainerRef.current) {
      const canvas = pageContainerRef.current.querySelector("canvas");
      if (canvas) {
        setPageWidth(canvas.offsetWidth);
        setPageHeight(canvas.offsetHeight);
        console.log(`[TEST] Canvas dimensions: ${canvas.offsetWidth}x${canvas.offsetHeight}`);
      }
    }
  }, []);

  useEffect(() => {
    if (!isOpen || !pageContainerRef.current) return;
    const resizeObserver = new ResizeObserver(() => updateCanvasDimensions());
    resizeObserver.observe(pageContainerRef.current);
    requestAnimationFrame(updateCanvasDimensions);
    return () => resizeObserver.disconnect();
  }, [isOpen, updateCanvasDimensions]);

  // ============================================================
  // TRANSFORMATION LOGIC - EDIT THIS TO TEST DIFFERENT FORMULAS
  // ============================================================
  function getHighlightStyle(bbox: BoundingBox, isError: boolean): React.CSSProperties {
    let left = bbox.left;
    let top = bbox.top;
    let width = bbox.width;
    let height = bbox.height;

    console.log(`[TEST] Raw bbox: left=${(left*100).toFixed(2)}%, top=${(top*100).toFixed(2)}%, w=${(width*100).toFixed(2)}%, h=${(height*100).toFixed(2)}%`);
    console.log(`[TEST] Internal rotation: ${pdfInternalRotation}°`);

    // ============================================================
    // >>> TRANSFORMATION GOES HERE <<<
    // Currently: NO TRANSFORMATION (pass-through)
    // ============================================================

    // TODO: Add transformation logic for 270° rotation here
    // Example formulas to try:
    //
    // Formula A (swap axes):
    // if (pdfInternalRotation === 270) {
    //   const newLeft = top;
    //   const newTop = 1 - left - width;
    //   left = newLeft;
    //   top = newTop;
    //   [width, height] = [height, width];
    // }
    //
    // Formula B (invert both):
    // if (pdfInternalRotation === 270) {
    //   left = 1 - top - height;
    //   top = 1 - left - width;
    // }

    console.log(`[TEST] Final: left=${(left*100).toFixed(2)}%, top=${(top*100).toFixed(2)}%`);

    const bgColor = isError ? "rgba(239, 68, 68, 0.3)" : "rgba(249, 115, 22, 0.25)";
    const borderColor = isError ? "#dc2626" : "#ea580c";

    // For very thin highlights (text lines), ensure minimum visibility
    // Match PDFPanel.tsx logic: detect text lines and apply larger minimum height
    const isTextLine = height < 0.02 && width > height * 3;
    const minHeight = isTextLine ? 0.025 : height; // 2.5% minimum for text lines
    const topAdjust = isTextLine ? top - (minHeight - height) / 2 : top;

    // Add horizontal padding for better visibility (1% on each side)
    const widthPadding = 0.01; // 1% padding
    const adjustedLeft = Math.max(0, left - widthPadding);
    const adjustedWidth = width + (widthPadding * 2);

    return {
      position: "absolute",
      left: `${adjustedLeft * 100}%`,
      top: `${Math.max(0, topAdjust) * 100}%`,
      width: `${adjustedWidth * 100}%`,
      height: `${minHeight * 100}%`,
      backgroundColor: bgColor,
      border: `3px solid ${borderColor}`,
      borderRadius: "4px",
      boxShadow: `0 0 16px ${isError ? "rgba(239, 68, 68, 0.9)" : "rgba(249, 115, 22, 0.8)"}`,
      pointerEvents: "none" as const,
      zIndex: 10,
    };
  }

  if (!isOpen) return null;

  return (
    <div
      ref={containerRef}
      className="fixed left-0 top-0 h-screen bg-white shadow-xl z-50 flex flex-col"
      style={{ width: `${panelWidth}vw` }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-yellow-50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-yellow-500 flex items-center justify-center">
            <span className="text-white font-bold">T</span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-800">TEST MODE - {documentName}</h3>
            <p className="text-xs text-yellow-700">
              Internal Rotation: {pdfInternalRotation}° | Canvas: {pageWidth}x{pageHeight}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-yellow-100"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto bg-gray-100 flex justify-center py-4">
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">Loading PDF...</p>
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full">
            <p className="text-red-500">{error}</p>
          </div>
        )}

        {pdfUrl && !error && (
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}
          >
            <div ref={pageContainerRef} className="relative bg-white shadow-xl rounded-lg">
              <Page
                pageNumber={currentPage}
                scale={scale}
                onLoadSuccess={onPageLoadSuccess}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />

              {/* Test Highlight Overlay */}
              {pageWidth > 0 && pageHeight > 0 && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    top: 0,
                    left: 0,
                    width: pageWidth,
                    height: pageHeight,
                    border: "3px solid blue",
                    boxSizing: "border-box",
                    zIndex: 20,
                  }}
                >
                  {/* Corner markers */}
                  <div style={{ position: "absolute", top: 0, left: 0, width: 15, height: 15, background: "blue", opacity: 0.7 }}>
                    <span style={{ color: "white", fontSize: 8 }}>TL</span>
                  </div>
                  <div style={{ position: "absolute", top: 0, right: 0, width: 15, height: 15, background: "green", opacity: 0.7 }}>
                    <span style={{ color: "white", fontSize: 8 }}>TR</span>
                  </div>
                  <div style={{ position: "absolute", bottom: 0, left: 0, width: 15, height: 15, background: "red", opacity: 0.7 }}>
                    <span style={{ color: "white", fontSize: 8 }}>BL</span>
                  </div>
                  <div style={{ position: "absolute", bottom: 0, right: 0, width: 15, height: 15, background: "yellow", opacity: 0.7 }}>
                    <span style={{ color: "white", fontSize: 8 }}>BR</span>
                  </div>

                  {/* Render test highlights */}
                  {TEST_HIGHLIGHTS.map((highlight, index) => {
                    const isError = highlight.type === "error";
                    const style = getHighlightStyle(highlight.bbox, isError);
                    const topPct = parseFloat((style.top as string).replace("%", ""));

                    return (
                      <React.Fragment key={index}>
                        {/* Label above highlight - uses same left position as highlight box */}
                        <div
                          style={{
                            position: "absolute",
                            left: style.left,
                            top: `${Math.max(0, topPct - 2.5)}%`,
                            backgroundColor: isError ? "#dc2626" : "#ea580c",
                            color: "white",
                            fontSize: "10px",
                            fontWeight: 600,
                            padding: "3px 8px",
                            borderRadius: "4px",
                            zIndex: 21,
                            whiteSpace: "nowrap",
                            boxShadow: isError ? "0 0 8px rgba(220, 38, 38, 0.8)" : "0 0 8px rgba(234, 88, 12, 0.6)",
                          }}
                        >
                          {highlight.text} {isError ? "(ERROR)" : ""}
                        </div>
                        {/* Highlight box */}
                        <div style={style} />
                      </React.Fragment>
                    );
                  })}
                </div>
              )}
            </div>
          </Document>
        )}
      </div>

      {/* Footer with test info */}
      <div className="px-4 py-3 border-t border-gray-200 bg-yellow-50">
        <div className="text-xs text-yellow-800">
          <strong>Test Highlights:</strong>
          {TEST_HIGHLIGHTS.map((h, i) => (
            <span key={i} className="ml-2">
              {h.text} ({(h.bbox.left * 100).toFixed(1)}%, {(h.bbox.top * 100).toFixed(1)}%)
            </span>
          ))}
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Edit getHighlightStyle() in PDFPanelTest.tsx to test transformation formulas
        </div>
      </div>
    </div>
  );
}

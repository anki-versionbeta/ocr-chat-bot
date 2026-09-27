# Test Queries for Multi-Agent GraphRAG System

**Document:** Sample Analysis Report (MFI Stability Samples)
**Process ID:** `53e654a3-d0ce-47ed-9d7f-d5d676958d80`
**Created:** February 12, 2026

Based on the sample document image showing a "Sample Analysis Report" with:
- Sample Analysis Summary (Batch Name, Project Name, User, Analysis Date/Time)
- ECD(um) statistics (Mean, Standard Deviation, Range, Mode, etc.)
- Particle Statistics Summary with Range/Count/Concentration tables

---

## Test Query Categories

### Category 1: Simple Value Lookup (Cell-based)
These queries target specific values in tables.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 1 | "What is the Batch Name?" | Line or Cell | Easy |
| 2 | "What is the Project Name?" | Cell | Easy |
| 3 | "What is the Mean ECD value?" | Cell | Easy |
| 4 | "What is the Particle Count?" | Cell | Easy |
| 5 | "What is the Analysis Date/Time?" | Cell | Easy |

### Category 2: Row Extraction (Cell-based)
These queries target entire rows from tables.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 6 | "Get all Count row values from the first ECD table" | Cell | Medium |
| 7 | "Get all Concentration values from the ECD table" | Cell | Medium |
| 8 | "Get the second Count row values only" | Cell | Hard |
| 9 | "Get all Range row values across all pages" | Cell | Hard |

### Category 3: Column Extraction (Cell-based)
These queries target entire columns.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 10 | "Extract all values from the >=1.00 <2.00 column" | Cell | Medium |
| 11 | "Get all values under the >=2.00 <4.00 range column" | Cell | Medium |

### Category 4: Cross-Page Aggregation (Cell-based)
These queries need data from multiple pages.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 12 | "Get Project Name and Count values from all pages" | Cell | Hard |
| 13 | "Compare Mean ECD values across all pages" | Cell | Hard |
| 14 | "Get second Count row with Project Name for each page" | Cell | Hard |

### Category 5: Metadata/Header Queries (Line-based)
These queries target text outside tables.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 15 | "What is the document title?" | Line | Easy |
| 16 | "Who is the User?" | Line or Cell | Easy |
| 17 | "What Method was used?" | Line | Medium |

### Category 6: Mixed Node Type Queries
These queries may need both Line and Cell nodes.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 18 | "Get Batch Name and all Count values" | Line + Cell | Hard |
| 19 | "Find Project Name from header and Concentration from table" | Mixed | Hard |

### Category 7: Structural Queries
These queries test path validation.

| # | Query | Expected Node Type | Difficulty |
|---|-------|-------------------|------------|
| 20 | "What tables exist on page 1?" | Table | Medium |
| 21 | "How many rows are in the ECD table?" | Cell | Medium |

---

## Recommended Test Order

### Phase 1: Simple Tests (Warm-up)
```
Query 1: "What is the Batch Name?"
Query 2: "What is the Project Name?"
Query 4: "What is the Particle Count?"
```

### Phase 2: Row Extraction Tests
```
Query 6: "Get all Count row values from the first ECD table"
Query 7: "Get all Concentration values from the ECD table"
```

### Phase 3: Hard Tests (Cross-page, Second row)
```
Query 8: "Get the second Count row values only"
Query 12: "Get Project Name and Count values from all pages"
Query 14: "Get second Count row with Project Name for each page"
```

### Phase 4: Topology Tests (Line vs Cell)
```
Query 15: "What is the document title?"
Query 18: "Get Batch Name and all Count values"
```

---

## Query Details for Testing

### Query 1: Simple Lookup
```
Query: "What is the Batch Name?"
Expected: "20251023_ABBV1451"
Node Type: Likely Line (from "Batch Name: 20251023_ABBV1451")
Tests: Basic retrieval
```

### Query 2: Project Name Lookup
```
Query: "What is the Project Name?"
Expected: "ABBV1451_S01996_3M_p5-Run003" (from page 1)
Node Type: Cell (from table header area)
Tests: Cell-based lookup
```

### Query 6: Full Row Extraction
```
Query: "Get all Count row values from the first ECD table"
Expected: Row with values like [2758, 561, 150, 69, 30, 12, 1, 0]
Node Type: Cell
Tests: Row extraction by label
```

### Query 8: Second Row Extraction (HARD)
```
Query: "Get the second Count row values only"
Expected: The SECOND "Count" row (not the first)
Node Type: Cell
Tests:
  - Finding rows by label
  - Differentiating between multiple rows with same label
  - Using row_index ordering
```

### Query 14: Complex Cross-Page (HARDEST)
```
Query: "Get second Count row with Project Name for each page"
Expected: 9 rows (one per page), each with Project Name + second Count values
Node Type: Cell (with Page join)
Tests:
  - Cross-page aggregation
  - Second row logic
  - Project Name from different table/location
  - Page as join point
```

---

## Test Results Tracking

| Query # | Query | Status | Node Type | Iterations | Notes |
|---------|-------|--------|-----------|------------|-------|
| 1 | Batch Name | [ ] | | | |
| 2 | Project Name | [ ] | | | |
| 4 | Particle Count | [ ] | | | |
| 6 | Count row values | [ ] | | | |
| 7 | Concentration values | [ ] | | | |
| 8 | Second Count row | [ ] | | | |
| 12 | Project + Count all pages | [ ] | | | |
| 14 | Second Count + Project | [ ] | | | |
| 15 | Document title | [ ] | | | |
| 18 | Batch Name + Count | [ ] | | | |

---

## Expected Improvements from NEV + Success Bank + Hard Constraints

| Scenario | Before | After | Why |
|----------|--------|-------|-----|
| Line data query | 40% success | 95% | Hard constraints force Line path |
| Second row query | 70% success | 95% | Better few-shot from Success Bank |
| Cross-page query | 60% success | 90% | Topology NEV catches bad paths |
| Mixed node query | 50% success | 85% | Constraints allow BOTH + Page join |

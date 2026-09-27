import sys
sys.stdout.reconfigure(encoding='utf-8')

print('='*120)
print('COMPARISON: Previous Fix vs Generic Entity Validation')
print('Using ACTUAL data from the document')
print('='*120)

USER_QUERY = "Get range values >=0.5, >=1, >=2, >=5, >=10, >=25, >=50 with batch name and project name"

print(f'''
USER QUERY: "{USER_QUERY}"

ACTUAL DATA IN DOCUMENT:
- Weaviate Headers (mixed): [">=1", ">=2", ">=4", ">=6", ">=9", ">=15", ">=30", ">=50", "Batch Name", "Project Name"]
- Data Snippet Range Row: col2=">=1", col3=">=2", col4=">=5", col5=">=10", col6=">=25", col7=">=50", col8="-", col9="-"
- ACTUAL valid columns: >=1, >=2, >=5, >=10, >=25, >=50 (cols 2-7)
- User asked for >=0.5 which DOES NOT EXIST!
''')

print('='*120)
print('APPROACH 1: TABLE STRUCTURE ANALYSIS (Limited to tables only)')
print('='*120)

print('''
WHAT IT DOES:
1. Parse data_snippet JSON
2. Find rows with "Range" label
3. Extract column headers: [>=1, >=2, >=5, >=10, >=25, >=50]
4. Detect >=0.5 is missing
5. Output: "Use col_index IN [2,3,4,5,6,7]"

LIMITATIONS:
- Only handles TABLE column headers
- Does NOT validate "batch name" (metadata field)
- Does NOT validate "project name" (metadata field)
- Does NOT tell LLM where to find batch name (Line vs Cell)
- Does NOT work for non-table documents
''')

print('='*120)
print('APPROACH 2: GENERIC ENTITY VALIDATION (Complete solution)')
print('='*120)

print('''
WHAT IT DOES:
1. Extract ALL entities from user query:
   - "range" (row label)
   - ">=0.5", ">=1", ">=2"... (column headers)
   - "batch name" (metadata)
   - "project name" (metadata)

2. Build index from ALL sources:
   - Weaviate headers
   - Data snippet content
   - Structural probe results

3. Validate EACH entity:
   +----------------+--------+--------------+------------------+
   | Entity         | Found? | Where?       | Action           |
   +----------------+--------+--------------+------------------+
   | "range"        | YES    | Cell nodes   | Use as-is        |
   | ">=0.5"        | NO     | -            | REMOVE           |
   | ">=1"          | YES    | Cell col 2   | Use as-is        |
   | ">=2"          | YES    | Cell col 3   | Use as-is        |
   | ">=5"          | YES    | Cell col 4   | Use as-is        |
   | ">=10"         | YES    | Cell col 5   | Use as-is        |
   | ">=25"         | YES    | Cell col 6   | Use as-is        |
   | ">=50"         | YES    | Cell col 7   | Use as-is        |
   | "batch name"   | YES    | LINE nodes   | Route to Line    |
   | "project name" | YES    | Cell nodes   | Route to Cell    |
   +----------------+--------+--------------+------------------+

4. Generate complete context for Logic Planner:
   - Valid columns: [>=1, >=2, >=5, >=10, >=25, >=50]
   - Column indices: [2, 3, 4, 5, 6, 7]
   - Corrections: ">=0.5 NOT FOUND, removed"
   - Data routing: "batch name" from LINE, "project name" from CELL
''')

print('='*120)
print('COMPARISON TABLE')
print('='*120)

print('''
+---------------------------+--------------------------------+--------------------------------+
| Aspect                    | Approach 1: Table Structure    | Approach 2: Entity Validation  |
+---------------------------+--------------------------------+--------------------------------+
| Scope                     | Only table columns             | ALL entities (any type)        |
+---------------------------+--------------------------------+--------------------------------+
| Handles "batch name"?     | NO                             | YES - validates & routes       |
+---------------------------+--------------------------------+--------------------------------+
| Handles "project name"?   | NO                             | YES - validates & routes       |
+---------------------------+--------------------------------+--------------------------------+
| Detects >=0.5 missing?    | YES                            | YES                            |
+---------------------------+--------------------------------+--------------------------------+
| Data source routing?      | NO                             | YES (Line vs Cell)             |
+---------------------------+--------------------------------+--------------------------------+
| Works for non-table docs? | NO                             | YES                            |
+---------------------------+--------------------------------+--------------------------------+
| Uses existing data?       | data_snippet only              | ALL sources combined           |
+---------------------------+--------------------------------+--------------------------------+
| VERDICT                   | Partial solution               | COMPLETE solution              |
+---------------------------+--------------------------------+--------------------------------+

CONCLUSION: Approach 2 is BETTER because it:
1. Validates ALL user query entities, not just table columns
2. Uses ALL existing data (Weaviate + data_snippet + structural probe)
3. Provides data source routing (which node type to use)
4. Works for ANY document type
5. Is ONE function that solves the COMPLETE problem
''')

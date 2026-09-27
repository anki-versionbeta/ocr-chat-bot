# AI Document Parser - Complete Business Demo Script

---

## WHY WE BUILT THIS

> "Before I show you the demo, let me explain **why** we built this tool.
>
> You might ask - we already have tools like go/ai for Q&A. Why do we need another one?
>
> Here's the difference:
>
> **Normal Q&A tools (go/ai):**
> - Good for general questions
> - Works on simple documents
> - No verification capability
> - No traceability
>
> **What our users actually need:**
> - Process 100+ page documents quickly
> - Extract specific parameters across ALL pages at once
> - **Verify** if the extracted value is correct - see it in the original PDF
> - Save hours of manual page-by-page searching
> - Trust the data with full audit trail
>
> **The problem:** Users upload large documents but they don't know exactly where the data is. They need to ask a question, get an answer, AND verify it's correct by seeing the source.
>
> **Our solution:** Extract + Verify in one place. Ask a question → Get answer → Click to see exactly where it came from in the PDF with highlight boxes."

---

## DEMO START - LOGIN PAGE

**[Show login page]**

> "Let's start from the beginning. This is our AI Document Parser.
>
> I'll log in with my credentials..."

**[Login]**

> "Once logged in, you see a clean interface. On the left - chat history for previous sessions. In the center - our assistant ready to help."

---

## STEP 1: UPLOAD A DOCUMENT

**[Click upload button or drag file]**

> "Let's upload a document. I have a stability report here - about 100 pages.
>
> In the traditional way, if someone asked you to find all the Ges.-Mittel values from this document, you would:
> 1. Open the PDF
> 2. Go page by page
> 3. Find the tables
> 4. Copy values manually
> 5. Paste into Excel
>
> **That's 2-3 hours of work.**
>
> Let's see what happens when we upload it here..."

**[Upload completes]**

> "Done. The system has processed all 100 pages - recognized tables, parameters, values. Everything is now searchable."

---

## STEP 2: ASK A QUESTION (EXTRACTION)

**[Type the prompt]**

```
Get all Ges.-Mittel. row values across all pages. Extract the charge parameter value. Export the results to Excel with charge as the header and operator as the header followed by the µm range columns.
```

> "Now I simply tell the system what I need. Plain English. No coding. No complex queries.
>
> I'm asking for:
> - Ges.-Mittel values from ALL pages
> - Charge and Operator information
> - Export to Excel with proper headers
>
> Let's see..."

**[Results appear + Excel downloads]**

> "There it is. All pages processed. Excel ready to download. **30 seconds** instead of 3 hours."

---

## STEP 3: VERIFICATION - THE KEY FEATURE

> "Now here's the **most important part** - and this is what makes us different from any other tool.
>
> You have the Excel. But how do you know it's correct? How do you verify?
>
> In other tools, you just have to trust the answer. Here, you can verify."

**[Type verification prompt]**

```
Show me the values of project name
```

> "Watch what happens..."

**[PDF panel opens with highlights]**

> "The system opens the original PDF and shows me **exactly where that data came from**.
>
> See these orange boxes? That's highlighting the exact cells where the values were extracted.
>
> **This is your audit trail. This is traceability.**
>
> If your manager asks 'Where did this number come from?' - one click, and you can show them."

---

## STEP 4: DRILL DOWN TO SPECIFIC PAGE

**[Type another prompt]**

```
Show me the batch name in page 23
```

> "I can also go to a specific page. Maybe I want to verify something on page 23.
>
> The system takes me directly there and highlights the exact field.
>
> No scrolling through 100 pages. No searching. Direct navigation with visual proof."

---

## STEP 5: CAPABILITIES OVERVIEW

**[Click Capabilities button to show modal]**

> "Let me quickly show you all the capabilities we've built:
>
> 1. **Multi-Page Extraction** - Process 100+ pages at once
> 2. **Visual Verification** - See source with highlight boxes
> 3. **Excel Export** - Structured data ready for analysis
> 4. **Pattern Learning** - System learns successful queries
> 5. **Batch Parameter Extraction** - Multiple parameters at once
> 6. **Natural Language Queries** - No technical knowledge needed"

---

## WHAT WE'VE ADDED & WHY

> "Let me explain the key features we've specifically built for your use cases:
>
> **1. Highlight Boxes (Bounding Box)**
> - **Why:** Users need to verify data is correct
> - **What it does:** Shows exact location in PDF where data was found
> - **Value:** Full traceability, audit-ready
>
> **2. Multi-Page Processing**
> - **Why:** Documents are 100+ pages, manual search takes hours
> - **What it does:** Extracts from ALL pages in one query
> - **Value:** Hours → Seconds
>
> **3. Excel Export with Custom Headers**
> - **Why:** Users need data in specific formats for their workflows
> - **What it does:** Exports with headers you specify
> - **Value:** No reformatting needed
>
> **4. Pattern Learning (Success Bank)**
> - **Why:** Users ask similar questions for similar documents
> - **What it does:** Remembers successful queries, suggests them next time
> - **Value:** Even faster over time, consistent results
>
> **5. Natural Language Interface**
> - **Why:** Not everyone knows technical query languages
> - **What it does:** Understands plain English requests
> - **Value:** Anyone can use it, no training needed"

---

## CLOSING

> "So to summarize:
>
> | Traditional Way | With AI Document Parser |
> |-----------------|------------------------|
> | 2-3 hours per document | 30 seconds |
> | Manual page-by-page search | Automatic extraction |
> | No verification | Click-to-verify with highlights |
> | Copy-paste errors | Direct Excel export |
> | Start fresh every time | Pattern learning |
>
> **The key difference from other Q&A tools:**
> - It's not just about getting an answer
> - It's about **verifying** that answer is correct
> - It's about **traceability** - showing where data came from
> - It's about **saving time** on large documents
>
> Any questions?"

---

## QUICK REFERENCE - DEMO PROMPTS

| Step | What to Type |
|------|--------------|
| **Extract data** | `Get all Ges.-Mittel. row values across all pages. Extract the charge parameter value. Export the results to Excel with charge as the header and operator as the header followed by the µm range columns.` |
| **Verify project** | `Show me the values of project name` |
| **Verify specific page** | `Show me the batch name in page 23` |

---

## COMMON QUESTIONS & ANSWERS

**Q: "Why not just use go/ai?"**
> "go/ai is great for general Q&A. But when you have a 100-page document and need to extract specific parameters from every page, verify the results, and export to Excel - that's where this tool shines. It's built for document-heavy workflows."

**Q: "How do I know the data is correct?"**
> "Click any result and the system shows you the exact source in the PDF with highlight boxes. Full traceability."

**Q: "What if I don't know where the data is?"**
> "That's exactly why we built this. You don't need to know. Just describe what you're looking for, and the system finds it across all pages."

**Q: "Can it handle different document formats?"**
> "Yes - the system learns document structures. It handles tables, merged cells, multi-page tables, and various layouts."

**Q: "How secure is it?"**
> "Everything runs in your secure environment. Documents stay within your infrastructure."

---

## DEMO FLOW SUMMARY

```
LOGIN
  ↓
"Why we built this" (vs go/ai)
  ↓
UPLOAD DOCUMENT
  ↓
"Traditional way = 2-3 hours"
  ↓
ASK QUESTION → GET EXCEL
  ↓
"30 seconds instead of hours"
  ↓
VERIFY → HIGHLIGHT BOXES
  ↓
"This is traceability"
  ↓
SHOW CAPABILITIES MODAL
  ↓
"What we added & why"
  ↓
CLOSE → QUESTIONS
```

---

*Demo Document - March 2026*

"""
Test Visual Audit Flow - Full Integration Test

Tests the complete visual audit pipeline:
1. Stage 1: Discovery with LLM-based query analysis
2. Page selection follow-up detection via context analysis
3. Stage 2: Deep analysis with Gemini multimodal

Test Query: "what is the calculated elapsed time?"
Process ID: b5b3648f-1da1-4ab5-bd3d-5f935c0288b5
Filename: BR-1003 1000962712.pdf

Run with:
    cd backend
    python test_visual_audit_flow.py
"""

import sys
import os

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.rag_orchestrator import get_rag_orchestrator
from services.visual_audit_service import (
    analyze_audit_query_with_llm,
    analyze_conversation_context
)

# Test configuration
PROCESS_ID = 'b5b3648f-1da1-4ab5-bd3d-5f935c0288b5'
FILENAME = 'BR-1003 1000962712.pdf'
TEST_QUERY = 'what is the calculated elapsed time?'


def test_query_analysis():
    """Test LLM-based query analysis."""
    print("\n" + "=" * 80)
    print("TEST 1: LLM Query Analysis")
    print("=" * 80)

    result = analyze_audit_query_with_llm(TEST_QUERY)

    print(f"\nQuery: '{TEST_QUERY}'")
    print(f"Query Type: {result.get('query_type')}")
    print(f"Identifier: {result.get('identifier')}")
    print(f"Identifier Type: {result.get('identifier_type')}")
    print(f"Search Keywords: {result.get('search_keywords')}")

    return result


def test_context_analysis_new_query():
    """Test context analysis for a NEW query (no history)."""
    print("\n" + "=" * 80)
    print("TEST 2: Context Analysis - New Query (No History)")
    print("=" * 80)

    result = analyze_conversation_context(
        query=TEST_QUERY,
        recent_messages=[]
    )

    print(f"\nQuery: '{TEST_QUERY}'")
    print(f"Is Page Selection: {result.get('is_page_selection')}")
    print(f"Action Type: {result.get('action_type')}")

    return result


def test_context_analysis_page_selection():
    """Test context analysis for page selection follow-up."""
    print("\n" + "=" * 80)
    print("TEST 3: Context Analysis - Page Selection Follow-up")
    print("=" * 80)

    # Simulate conversation where assistant asked for page selection
    recent_messages = [
        {
            "role": "user",
            "content": "check the elapsed time calculations"
        },
        {
            "role": "assistant",
            "content": """I found relevant data for audit on these pages:

**Page 31**: Step 7.3 - Mix Start Time: 10:45, Duration: 15 min...
**Page 45**: Step 8.1 - Mix Start Time: 11:30, Duration: 20 min...

Which page do you want me to **deep analyze**? (Max 3 pages)"""
        }
    ]

    # User's follow-up selecting pages
    user_query = "31 and 45"

    result = analyze_conversation_context(
        query=user_query,
        recent_messages=recent_messages
    )

    print(f"\nConversation History:")
    for msg in recent_messages:
        role = msg['role'].upper()
        content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
        print(f"  {role}: {content}")

    print(f"\nCurrent Query: '{user_query}'")
    print(f"\nContext Analysis Result:")
    print(f"  Is Page Selection: {result.get('is_page_selection')}")
    print(f"  Action Type: {result.get('action_type')}")
    print(f"  Pages: {result.get('pages')}")
    print(f"  Original Query: {result.get('original_query')}")

    return result


def test_full_visual_audit_flow():
    """Test the complete visual audit flow via RAG orchestrator."""
    print("\n" + "=" * 80)
    print("TEST 4: Full Visual Audit Flow (Stage 1 Discovery)")
    print("=" * 80)

    orchestrator = get_rag_orchestrator()

    print(f"\nQuery: '{TEST_QUERY}'")
    print(f"Process ID: {PROCESS_ID[:8]}...")
    print(f"Filename: {FILENAME}")

    # Test with no chat history (new query)
    result = orchestrator.process_query_sync(
        query=TEST_QUERY,
        process_id=PROCESS_ID,
        filename=FILENAME,
        recent_messages=None,
        use_cache=False  # Skip cache for testing
    )

    print(f"\n--- RESULT ---")
    print(f"Query Type: {result.get('query_type')}")
    print(f"Stage: {result.get('stage')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"Needs Page Selection: {result.get('needs_page_selection')}")
    print(f"Pages Found: {result.get('pages_found', [])[:5]}...")  # First 5

    print(f"\nAnswer Preview:")
    answer = result.get('answer', '')[:500]
    print(answer + ("..." if len(result.get('answer', '')) > 500 else ""))

    return result


def test_page_selection_followup():
    """Test page selection follow-up via RAG orchestrator."""
    print("\n" + "=" * 80)
    print("TEST 5: Page Selection Follow-up Flow")
    print("=" * 80)

    orchestrator = get_rag_orchestrator()

    # Simulate chat history where assistant asked for page selection
    recent_messages = [
        {
            "role": "user",
            "content": "what is the calculated elapsed time?"
        },
        {
            "role": "assistant",
            "content": """**Parallel Discovery Complete** (6 agents analyzed 30 chunks)

**Time Values:**
  - Page 31: Step 7.3 elapsed time calculations (relevance: 0.9)
  - Page 45: Step 8.1 duration verification (relevance: 0.8)

**Pages with audit targets:** 31, 45, 48

Which page(s) do you want me to **deep analyze**? (Max 3 pages)"""
        }
    ]

    # User selects page 31
    follow_up_query = "page 31"

    print(f"\nFollow-up Query: '{follow_up_query}'")
    print(f"Chat History Messages: {len(recent_messages)}")

    result = orchestrator.process_query_sync(
        query=follow_up_query,
        process_id=PROCESS_ID,
        filename=FILENAME,
        recent_messages=recent_messages,
        use_cache=False
    )

    print(f"\n--- RESULT ---")
    print(f"Query Type: {result.get('query_type')}")
    print(f"Stage: {result.get('stage')}")
    print(f"Pages Analyzed: {result.get('pages_analyzed')}")

    print(f"\nAnswer Preview:")
    answer = result.get('answer', '')[:800]
    print(answer + ("..." if len(result.get('answer', '')) > 800 else ""))

    return result


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("VISUAL AUDIT FLOW - INTEGRATION TEST")
    print("=" * 80)

    # Run tests
    test_query_analysis()
    test_context_analysis_new_query()
    test_context_analysis_page_selection()
    test_full_visual_audit_flow()

    # Uncomment to test page selection follow-up (requires PDF file)
    # test_page_selection_followup()

    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)

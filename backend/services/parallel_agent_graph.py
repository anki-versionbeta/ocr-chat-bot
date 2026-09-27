"""
Parallel Agent Graph for RAG - Using LangGraph

This module implements a parallel agent architecture for handling large
numbers of chunks. Instead of sending all chunks to one agent (which causes
confusion and inaccurate citations), we split chunks across multiple agents
running in parallel.

Architecture:
    Query → Retrieve 25 chunks → Split into 5 groups → 5 Parallel Agents → Merge Results

Decision Logic:
    - EXPLORATORY queries ("which sections have...", "list all...", "where does X appear")
      → Use parallel agents (need broad coverage)
    - SPECIFIC queries ("what is the value of X in step Y")
      → Use single agent (need precise answer from top chunks)
"""

import asyncio
import logging
import re
import json
from typing import Dict, List, Any, Optional, TypedDict
from concurrent.futures import ThreadPoolExecutor

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from services.answer_synthesizer import synthesize_answer_sync, build_context_from_chunks, build_cell_grounding_summary
from services.reference_extractor import extract_references, build_grounding_map

logger = logging.getLogger("ocr-chatbot.parallel_agent")


# =============================================================================
# STATE DEFINITION
# =============================================================================

class ParallelAgentState(TypedDict):
    """State for the parallel agent graph."""
    query: str
    filename: str
    chunks: List[Dict[str, Any]]
    chunk_groups: List[List[Dict[str, Any]]]
    agent_results: List[Dict[str, Any]]
    final_answer: str
    final_references: List[Dict[str, Any]]
    final_confidence: float
    query_type: str  # "exploratory" or "specific"
    max_agents: int  # Phase 8: Configurable agent count (1, 5, or 8)
    chunks_per_agent: int  # Phase 8: Chunks per agent


# =============================================================================
# QUERY TYPE DETECTION - CHUNK-BASED (NO REGEX)
# =============================================================================

# REMOVED: Hardcoded regex patterns that caused misclassification
# The routing decision is now based on CHUNK COUNT, not query patterns.
# If we have many chunks (>5), we use parallel agents to ensure we don't miss data.
# Intent classification is handled by the LLM-based intent_classifier.py


def detect_query_type(query: str, num_chunks: int = 0) -> str:
    """
    Determine routing based on chunk count, NOT regex patterns.

    The old regex-based detection was causing issues:
    - "what is the elapsed mix time?" matched 'what\\s+is\\s+the\\s+.+\\s+time' as SPECIFIC
    - This sent 25 chunks to a single agent, losing most of the data

    Now we simply use chunk count:
    - If we have many chunks (>5), use parallel agents to cover all data
    - If we have few chunks (<=5), single agent is sufficient

    Args:
        query: User's question (kept for logging)
        num_chunks: Number of chunks to process

    Returns:
        "exploratory" (parallel) or "specific" (single)
    """
    # Simple chunk-based routing - NO REGEX PATTERNS
    if num_chunks > 5:
        logger.info(f"Query routing: EXPLORATORY (parallel) - {num_chunks} chunks to process")
        return "exploratory"
    else:
        logger.info(f"Query routing: SPECIFIC (single) - only {num_chunks} chunks")
        return "specific"


# =============================================================================
# PARALLEL AGENT NODES
# =============================================================================

def split_chunks_node(state: ParallelAgentState) -> ParallelAgentState:
    """Split chunks into groups for parallel processing.

    Phase 8: Respects max_agents and chunks_per_agent from ExecutionPlan.
    """
    chunks = state["chunks"]
    max_agents = state.get("max_agents", 5)
    chunks_per_group = state.get("chunks_per_agent", 5)

    # Split into groups — process ALL chunks, scale agents dynamically
    groups = []
    for i in range(0, len(chunks), chunks_per_group):
        group = chunks[i:i + chunks_per_group]
        if group:
            groups.append(group)

    # If we have more groups than max_agents, increase chunks_per_group to fit
    # This ensures NO chunks are dropped
    if len(groups) > max_agents:
        balanced_size = max(1, -(-len(chunks) // max_agents))  # Ceiling division
        groups = []
        for i in range(0, len(chunks), balanced_size):
            group = chunks[i:i + balanced_size]
            if group:
                groups.append(group)

    logger.info(f"Split {len(chunks)} chunks into {len(groups)} groups (max_agents={max_agents}, chunks_per_group={chunks_per_group})")

    return {**state, "chunk_groups": groups}


def process_agent_group(query: str, chunks: List[Dict], group_idx: int, filename: str) -> Dict[str, Any]:
    """
    Process a single group of chunks with an agent.
    This runs in a thread for parallel execution.
    """
    try:
        # Use existing answer synthesizer
        result = synthesize_answer_sync(
            query=query,
            chunks=chunks,
            filename=filename
        )

        # Add group info
        result["group_idx"] = group_idx
        result["chunk_indices"] = [c.get("chunk_index") for c in chunks]
        result["pages"] = list(set([c.get("page") for c in chunks]))

        logger.info(f"Agent {group_idx} processed chunks from pages {result['pages']}")

        return result

    except Exception as e:
        logger.error(f"Agent {group_idx} error: {e}")
        return {
            "answer": "",
            "cell_ids": [],
            "confidence": 0,
            "group_idx": group_idx,
            "error": str(e)
        }


def parallel_agents_node(state: ParallelAgentState) -> ParallelAgentState:
    """Run multiple agents in parallel, one per chunk group.

    Phase 8: Uses configurable max_agents from ExecutionPlan.
    """
    query = state["query"]
    filename = state["filename"]
    chunk_groups = state["chunk_groups"]
    max_agents = state.get("max_agents", 5)

    results = []

    # Use ThreadPoolExecutor for parallel execution
    # Phase 8: max_workers set to max_agents
    with ThreadPoolExecutor(max_workers=max_agents) as executor:
        futures = []
        for idx, group in enumerate(chunk_groups):
            future = executor.submit(
                process_agent_group,
                query,
                group,
                idx,
                filename
            )
            futures.append(future)

        # Collect results
        for future in futures:
            try:
                result = future.result(timeout=30)
                results.append(result)
            except Exception as e:
                logger.error(f"Agent future error: {e}")

    logger.info(f"Parallel agents completed: {len(results)} results")

    return {**state, "agent_results": results}


def merge_results_node(state: ParallelAgentState) -> ParallelAgentState:
    """Merge results from all parallel agents."""
    agent_results = state["agent_results"]
    chunks = state["chunks"]
    query_type = state["query_type"]

    # Phrases that indicate "not found" - these should be filtered out
    NOT_FOUND_PHRASES = [
        "cannot be determined",
        "not provided",
        "not found",
        "not available",
        "no information",
        "not explicitly",
        "not mentioned",
        "does not contain",
        "doesn't contain",
        "unable to find",
        "without clarification",
        "cannot provide",
        "not documented",
        "no specific",
        "not in the context",
        "not in the provided"
    ]

    def is_valid_finding(answer: str, confidence: float) -> bool:
        """Check if answer is a real finding, not a 'not found' message."""
        if not answer or confidence < 0.5:
            return False
        answer_lower = answer.lower()
        for phrase in NOT_FOUND_PHRASES:
            if phrase in answer_lower:
                return False
        return True

    # Collect all answers that have content and are not errors
    valid_results = [r for r in agent_results if r.get("answer") and not r.get("error")]

    if not valid_results:
        return {
            **state,
            "final_answer": "I couldn't find relevant information in the document.",
            "final_references": [],
            "final_confidence": 0.0
        }

    # Collect only REAL findings (filter out "not found" messages)
    all_cell_ids = []
    all_answers = []
    total_confidence = 0
    valid_finding_count = 0
    found_table_chunk_index = None

    for result in valid_results:
        answer = result.get("answer", "")
        confidence = result.get("confidence", 0)

        # Only include real findings
        if is_valid_finding(answer, confidence):
            cell_ids = result.get("cell_ids", [])
            all_cell_ids.extend(cell_ids)

            # Preserve table_chunk_index from any agent that found a table
            if result.get("table_chunk_index") is not None and found_table_chunk_index is None:
                found_table_chunk_index = result["table_chunk_index"]

            if answer not in all_answers:
                all_answers.append(answer)

            total_confidence += confidence
            valid_finding_count += 1

    # If no valid findings after filtering, return not found
    if not all_answers:
        return {
            **state,
            "final_answer": "I couldn't find relevant information about this in the document.",
            "final_references": [],
            "final_confidence": 0.0
        }

    # Build merged answer based on query type
    if query_type == "exploratory":
        # For exploratory, list all findings
        if len(all_answers) > 1:
            merged_answer = "Based on the document, I found the following:\n\n"
            for i, answer in enumerate(all_answers, 1):
                merged_answer += f"{i}. {answer}\n\n"
        else:
            merged_answer = all_answers[0] if all_answers else "No information found."
    else:
        # For specific, use the highest confidence answer from valid findings
        valid_finding_results = [r for r in valid_results if is_valid_finding(r.get("answer", ""), r.get("confidence", 0))]
        if valid_finding_results:
            best_result = max(valid_finding_results, key=lambda x: x.get("confidence", 0))
            merged_answer = best_result.get("answer", "")
            all_cell_ids = best_result.get("cell_ids", [])
        else:
            merged_answer = all_answers[0] if all_answers else "No information found."

    # Extract references using all cell_ids
    grounding_map = build_grounding_map(chunks)
    references = []

    for cell_id in set(all_cell_ids):
        # Cell IDs from synthesize_answer may have "cell:" or "line:" prefix, grounding map keys don't
        # Try both formats: "cell:339:31-22" -> "339:31-22", "line:1075:uuid" -> "1075:uuid"
        lookup_id = cell_id
        if cell_id.startswith("cell:"):
            lookup_id = cell_id.replace("cell:", "", 1)
        elif cell_id.startswith("line:"):
            lookup_id = cell_id.replace("line:", "", 1)

        if lookup_id in grounding_map:
            data = grounding_map[lookup_id]
            references.append({
                "page": data.get("page", 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", ""),
                "type": data.get("type", "cell")
            })
        elif cell_id in grounding_map:
            # Fallback to original cell_id
            data = grounding_map[cell_id]
            references.append({
                "page": data.get("page", 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", ""),
                "type": data.get("type", "cell")
            })

    # If no cell references but a table was identified, use the table's bbox
    if not references and found_table_chunk_index is not None:
        from .reference_extractor import get_chunk_bbox
        for chunk in chunks:
            if chunk.get('chunk_type') == 'table' and chunk.get('chunk_index') == found_table_chunk_index:
                chunk_bbox = get_chunk_bbox(chunk)
                if chunk_bbox.get('width', 0) > 0 and chunk_bbox.get('height', 0) > 0:
                    references.append({
                        'page': chunk.get('page', 1),
                        'bbox': chunk_bbox,
                        'cell_id': f"table_{found_table_chunk_index}",
                        'text': 'Table',
                        'type': 'table_layout'
                    })
                    logger.info(f"Using table chunk {found_table_chunk_index} bbox as reference (no cell_ids)")
                break

    avg_confidence = total_confidence / valid_finding_count if valid_finding_count > 0 else 0

    logger.info(f"Merged {valid_finding_count} valid findings (filtered from {len(valid_results)} agents), {len(references)} references")

    return {
        **state,
        "final_answer": merged_answer,
        "final_references": references,
        "final_confidence": avg_confidence,
        "table_chunk_index": found_table_chunk_index
    }


# =============================================================================
# SINGLE AGENT (for specific queries)
# =============================================================================

def single_agent_node(state: ParallelAgentState) -> ParallelAgentState:
    """Process with single agent using top 5 chunks only."""
    query = state["query"]
    filename = state["filename"]
    chunks = state["chunks"][:5]  # Only top 5

    result = synthesize_answer_sync(
        query=query,
        chunks=chunks,
        filename=filename
    )

    # Extract references
    grounding_map = build_grounding_map(state["chunks"])  # Use all chunks for grounding
    references = []

    for cell_id in result.get("cell_ids", []):
        # Cell IDs from synthesize_answer may have "cell:" or "line:" prefix, grounding map keys don't
        lookup_id = cell_id
        if cell_id.startswith("cell:"):
            lookup_id = cell_id.replace("cell:", "", 1)
        elif cell_id.startswith("line:"):
            lookup_id = cell_id.replace("line:", "", 1)

        if lookup_id in grounding_map:
            data = grounding_map[lookup_id]
            references.append({
                "page": data.get("page", 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", ""),
                "type": data.get("type", "cell")
            })
        elif cell_id in grounding_map:
            data = grounding_map[cell_id]
            references.append({
                "page": data.get("page", 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", ""),
                "type": data.get("type", "cell")
            })

    # If no cell references but a table was identified, use the table's bbox
    single_table_chunk_index = result.get("table_chunk_index")
    if not references and single_table_chunk_index is not None:
        from .reference_extractor import get_chunk_bbox
        for chunk in state["chunks"]:
            if chunk.get('chunk_type') == 'table' and chunk.get('chunk_index') == single_table_chunk_index:
                chunk_bbox = get_chunk_bbox(chunk)
                if chunk_bbox.get('width', 0) > 0 and chunk_bbox.get('height', 0) > 0:
                    references.append({
                        'page': chunk.get('page', 1),
                        'bbox': chunk_bbox,
                        'cell_id': f"table_{single_table_chunk_index}",
                        'text': 'Table',
                        'type': 'table_layout'
                    })
                    logger.info(f"Single agent: using table chunk {single_table_chunk_index} bbox")
                break

    return {
        **state,
        "final_answer": result.get("answer", ""),
        "final_references": references,
        "final_confidence": result.get("confidence", 0.5),
        "table_chunk_index": single_table_chunk_index,
        "agent_results": [result]
    }


# =============================================================================
# ROUTING LOGIC
# =============================================================================

def route_by_query_type(state: ParallelAgentState) -> str:
    """Route to parallel or single agent based on query type."""
    query_type = state["query_type"]

    if query_type == "exploratory":
        logger.info("Routing to PARALLEL agents")
        return "parallel"
    else:
        logger.info("Routing to SINGLE agent")
        return "single"


# =============================================================================
# BUILD GRAPH
# =============================================================================

def build_parallel_agent_graph():
    """Build the LangGraph workflow for parallel agent processing."""

    if not LANGGRAPH_AVAILABLE:
        logger.warning("LangGraph not available, using fallback")
        return None

    # Create graph
    workflow = StateGraph(ParallelAgentState)

    # Add nodes
    workflow.add_node("split_chunks", split_chunks_node)
    workflow.add_node("parallel_agents", parallel_agents_node)
    workflow.add_node("merge_results", merge_results_node)
    workflow.add_node("single_agent", single_agent_node)

    # Add conditional routing from start
    workflow.add_conditional_edges(
        "__start__",
        route_by_query_type,
        {
            "parallel": "split_chunks",
            "single": "single_agent"
        }
    )

    # Parallel path
    workflow.add_edge("split_chunks", "parallel_agents")
    workflow.add_edge("parallel_agents", "merge_results")
    workflow.add_edge("merge_results", END)

    # Single path
    workflow.add_edge("single_agent", END)

    return workflow.compile()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

# Compile graph once at module load
PARALLEL_GRAPH = build_parallel_agent_graph() if LANGGRAPH_AVAILABLE else None


async def run_parallel_agents(
    query: str,
    chunks: List[Dict[str, Any]],
    filename: str = "document",
    max_agents: int = 5,
    chunks_per_agent: int = 5,
    focus_entities: List[str] = None,
    relevance_rule: str = None
) -> Dict[str, Any]:
    """
    Run the parallel agent workflow with configurable agent count.

    Phase 8: Dynamic agent allocation based on ExecutionPlan:
    - max_agents=1: Single agent fast path (precision queries)
    - max_agents=5: Standard parallel (exploratory queries)
    - max_agents=8: Heavy lift (exhaustive queries)

    Phase 8 Enhancement: Query-Focused Multi-Agent
    - focus_entities: Values that MUST be in the answer (e.g., lot number)
    - relevance_rule: Rule for filtering relevant results
    - Returns agent_findings for Final Synthesis Agent to filter

    Args:
        query: User's question
        chunks: Retrieved chunks to process
        filename: Document filename
        max_agents: Maximum number of parallel agents (default: 5)
        chunks_per_agent: Chunks per agent (default: 5)
        focus_entities: Optional list of entities that MUST be in results
        relevance_rule: Optional rule for filtering relevant information

    Returns:
        Dict with answer, references, confidence, and agent_findings for Final Synthesis
    """
    # Phase 8: Force query type based on max_agents
    # max_agents=1 means single agent (precision), otherwise exploratory (parallel)
    if max_agents == 1:
        query_type = "specific"  # Single agent path
        logger.info(f"Forced SINGLE agent path (max_agents=1)")
    else:
        # Detect query type based on CHUNK COUNT
        query_type = detect_query_type(query, num_chunks=len(chunks))

    # Initialize state with Phase 8 configurable agent count
    initial_state: ParallelAgentState = {
        "query": query,
        "filename": filename,
        "chunks": chunks,
        "chunk_groups": [],
        "agent_results": [],
        "final_answer": "",
        "final_references": [],
        "final_confidence": 0.0,
        "query_type": query_type,
        "max_agents": max_agents,
        "chunks_per_agent": chunks_per_agent
    }

    logger.info(f"Parallel agents config: max_agents={max_agents}, chunks_per_agent={chunks_per_agent}, query_type={query_type}")

    if PARALLEL_GRAPH:
        # Run LangGraph workflow
        try:
            result = await asyncio.to_thread(PARALLEL_GRAPH.invoke, initial_state)

            # Phase 8: Build agent_findings for Final Synthesis Agent
            agent_results = result.get("agent_results", [])
            agent_findings = []
            for agent_result in agent_results:
                if agent_result.get("answer") and "not found" not in agent_result.get("answer", "").lower():
                    agent_findings.append({
                        "answer": agent_result.get("answer", ""),
                        "confidence": agent_result.get("confidence", 0),
                        "pages": agent_result.get("pages", []),
                        "cell_ids": agent_result.get("cell_ids", []),
                        "group_idx": agent_result.get("group_idx", 0)
                    })

            return {
                "answer": result.get("final_answer", ""),
                "references": result.get("final_references", []),
                "confidence": result.get("final_confidence", 0.5),
                "query_type": query_type,
                "agents_used": len(agent_results),
                "cell_ids": [r.get("cell_id") for r in result.get("final_references", [])],
                "table_chunk_index": result.get("table_chunk_index"),
                "agent_findings": agent_findings  # Phase 8: For Final Synthesis
            }
        except Exception as e:
            logger.error(f"LangGraph error: {e}")
            # Fallback to single agent
            return await _fallback_single_agent(query, chunks, filename, focus_entities, relevance_rule)
    else:
        # Fallback without LangGraph
        return await _fallback_single_agent(query, chunks, filename, focus_entities, relevance_rule)


async def _fallback_single_agent(
    query: str,
    chunks: List[Dict[str, Any]],
    filename: str,
    focus_entities: List[str] = None,
    relevance_rule: str = None
) -> Dict[str, Any]:
    """Fallback to single agent when LangGraph not available."""
    result = synthesize_answer_sync(
        query=query,
        chunks=chunks[:5],
        filename=filename,
        focus_entities=focus_entities,
        relevance_rule=relevance_rule
    )

    grounding_map = build_grounding_map(chunks)
    references = []

    for cell_id in result.get("cell_ids", []):
        if cell_id in grounding_map:
            data = grounding_map[cell_id]
            references.append({
                "page": data.get("page", 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", "")
            })

    # Phase 8: Build agent_findings for fallback (single agent = 1 finding)
    agent_findings = []
    if result.get("answer") and "not found" not in result.get("answer", "").lower():
        agent_findings.append({
            "answer": result.get("answer", ""),
            "confidence": result.get("confidence", 0),
            "pages": list(set(c.get("page") for c in chunks[:5] if c.get("page"))),
            "cell_ids": result.get("cell_ids", []),
            "group_idx": 0
        })

    # If no cell references but a table was identified, use table bbox
    fallback_table_idx = result.get("table_chunk_index")
    if not references and fallback_table_idx is not None:
        from .reference_extractor import get_chunk_bbox
        for chunk in chunks:
            if chunk.get('chunk_type') == 'table' and chunk.get('chunk_index') == fallback_table_idx:
                chunk_bbox = get_chunk_bbox(chunk)
                if chunk_bbox.get('width', 0) > 0 and chunk_bbox.get('height', 0) > 0:
                    references.append({
                        'page': chunk.get('page', 1),
                        'bbox': chunk_bbox,
                        'cell_id': f"table_{fallback_table_idx}",
                        'text': 'Table',
                        'type': 'table_layout'
                    })
                break

    return {
        "answer": result.get("answer", ""),
        "references": references,
        "confidence": result.get("confidence", 0.5),
        "query_type": "specific",
        "agents_used": 1,
        "cell_ids": result.get("cell_ids", []),
        "table_chunk_index": fallback_table_idx,
        "agent_findings": agent_findings  # Phase 8: For Final Synthesis
    }


def run_parallel_agents_sync(
    query: str,
    chunks: List[Dict[str, Any]],
    filename: str = "document",
    max_agents: int = 5,
    chunks_per_agent: int = 5,
    focus_entities: List[str] = None,
    relevance_rule: str = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for run_parallel_agents with configurable agent count.

    Phase 8: Supports dynamic agent count based on ExecutionPlan:
    - max_agents=1: Single agent fast path (precision queries)
    - max_agents=5: Standard parallel (exploratory queries)
    - max_agents=8: Heavy lift (exhaustive queries)

    Phase 8 Enhancement: Query-Focused Multi-Agent
    - focus_entities: Values that MUST be in the answer (e.g., lot number)
    - relevance_rule: Rule for filtering relevant results

    Args:
        query: User's question
        chunks: Retrieved chunks to process
        filename: Document filename
        max_agents: Maximum number of parallel agents (default: 5)
        chunks_per_agent: Chunks per agent (default: 5)
        focus_entities: Optional list of entities that MUST be in results
        relevance_rule: Optional rule for filtering relevant information

    Returns:
        Dict with answer, references, confidence, and agent_findings for Final Synthesis
    """
    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # If we get here, we're in an async context - use thread pool
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                run_parallel_agents(query, chunks, filename, max_agents, chunks_per_agent, focus_entities, relevance_rule)
            )
            return future.result(timeout=60)
    except RuntimeError:
        # No running event loop - safe to use asyncio.run()
        return asyncio.run(run_parallel_agents(query, chunks, filename, max_agents, chunks_per_agent, focus_entities, relevance_rule))


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Parallel Agent Graph Module")
    print(f"LangGraph available: {LANGGRAPH_AVAILABLE}")
    print(f"Graph compiled: {PARALLEL_GRAPH is not None}")

    # Test chunk-based query type detection (NO REGEX)
    print("\nChunk-Based Query Type Detection:")
    print("  (Routing is based on chunk count, not query patterns)")
    print()

    test_cases = [
        ("what is the elapsed mix time?", 25),  # Many chunks -> parallel
        ("what is the elapsed mix time?", 5),   # Few chunks -> single
        ("show me the batch number", 3),        # Few chunks -> single
        ("list all elapsed times", 20),         # Many chunks -> parallel
    ]

    for query, num_chunks in test_cases:
        qtype = detect_query_type(query, num_chunks=num_chunks)
        print(f"  [{qtype.upper():12}] chunks={num_chunks:2} | {query}")

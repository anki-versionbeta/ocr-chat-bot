"""
RAG Orchestrator for Phase 4 + Phase 6 - Multi-Agent RAG Orchestration with Neo4j

This is the main orchestration module that coordinates all RAG components:
1. Semantic Cache - Check for similar cached queries
2. Intent Classifier - Route to appropriate pipeline
3. Question Rephraser - Generate query variations
4. Weaviate Search - Parallel hybrid search
5. Neo4j Service - Structural and hybrid queries (Phase 6)
6. Answer Synthesizer - Generate answer with cell references
7. Reference Extractor - Extract bbox for PDF highlighting
8. Cache Update - Store response for future queries

Intent Routing:
- vector_only: Weaviate only (90% of queries)
- structural: Neo4j only (page finding, table structure)
- hybrid_semantic_structural: Weaviate → Neo4j (column extraction across pages)
- extraction: Neo4j bulk extraction (export all data)

Usage:
    orchestrator = RAGOrchestrator()
    response = await orchestrator.process_query(
        query="What is the batch number?",
        process_id="uuid-here",
        filename="document.pdf"
    )

Updated: February 11, 2026 - Phase 6 Neo4j Integration
"""

import os
import json
import logging
import asyncio
import requests
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

# Import Phase 4 components
from .semantic_cache import SemanticCache, get_semantic_cache
from .intent_classifier import (
    classify_intent, QueryIntent, classify_intent_sync,
    classify_with_plan, ExecutionPlan, AgentStrategy, get_execution_plan
)
from .question_rephraser import (
    rephrase_question_sync,
    detect_row_col_query,
    detect_page_filter,
    resolve_context_references
)
from .answer_synthesizer import (
    synthesize_answer_sync,
    add_confidence_disclaimer
)
from .reference_extractor import (
    extract_references,
    format_references_for_frontend,
    build_response_with_references
)
from .weaviate_indexer import WeaviateIndexer
from .flashrank_reranker import get_reranker
from .parallel_agent_graph import run_parallel_agents_sync, detect_query_type

# Import Phase 6 Neo4j components
from .neo4j_service import get_neo4j_service, Neo4jService
from .cypher_templates import get_cypher_templates, CypherTemplates
from .langchain_neo4j_service import get_langchain_neo4j_service, execute_hybrid_query

# Import Multi-Agent Cypher Service (advanced dynamic Cypher generation)
from .multiagent_cypher_service import run_fewshot_cypher_generation

# Import Phase 7 Visual Audit Service (Gemini multimodal)
from .visual_audit_service import get_visual_audit_service, analyze_conversation_context

load_dotenv()

logger = logging.getLogger("ocr-chatbot.rag_orchestrator")


class RAGOrchestrator:
    """
    Main orchestrator for multi-agent RAG queries.

    Phase 4 Flow (vector_only):
    Query → Cache Check → Intent → Rephrase → Search → Synthesize → Extract Refs → Response

    Phase 6 Flow (structural/hybrid/extraction):
    Query → Cache Check → Intent → Route to Neo4j → Synthesize → Response
    """

    def __init__(self):
        """Initialize the orchestrator with all components."""
        self.cache = get_semantic_cache()
        self.weaviate = WeaviateIndexer()
        self.neo4j = get_neo4j_service()
        self.cypher_templates = get_cypher_templates()
        self.langchain_neo4j = get_langchain_neo4j_service()  # Phase 6: Dynamic Cypher
        self.reranker = get_reranker()  # FlashRank reranker for BQ optimization
        self.visual_audit = get_visual_audit_service()  # Phase 7: Visual Audit with Gemini
        self.executor = ThreadPoolExecutor(max_workers=5)

        logger.info(f"RAGOrchestrator initialized (Neo4j connected: {self.neo4j.is_connected}, LangChain Neo4j: {self.langchain_neo4j.is_connected}, FlashRank: {self.reranker.is_available})")

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for query (used for cache lookup)."""
        return self.weaviate.generate_embedding(query)

    def _parallel_search(
        self,
        queries: List[str],
        process_id: str,
        limit_per_query: int = 5,
        use_reranking: bool = True,
        page_filter: int = None,
        alpha: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Execute search with dynamic alpha and optional FlashRank reranking.

        OPTIMIZED FLOW:
        1. Single query search (no rephrasing needed)
        2. Dynamic alpha: 0.0 for exploratory (pure BM25), 0.5 for specific (hybrid)
        3. Overfetch for reranking (fetch more, rerank to top_k)
        4. FlashRank cross-encoder reranking (SKIPPED for exploratory queries)
        5. Optional page filtering when user specifies "from page X"

        NOTE: For exploratory queries (alpha=0.0), we SKIP FlashRank reranking
        because cross-encoder semantic matching pushes out keyword matches.
        BM25 already finds the right documents by keyword; reranking hurts recall.

        Args:
            queries: List of query variations (usually just 1 now)
            process_id: Document filter
            limit_per_query: Max results per query
            use_reranking: Whether to use FlashRank reranking
            page_filter: Optional page number to filter results (e.g., user says "from page 5")
            alpha: Search alpha (0.0=BM25 only, 0.5=hybrid, 1.0=vector only)

        Returns:
            Reranked and deduplicated results
        """
        all_results = []
        seen_chunk_ids = set()

        # Overfetch for reranking - fetch more results to rerank from
        # 8x multiplier to get enough chunks for parallel agent processing
        overfetch_limit = limit_per_query * 8 if use_reranking else limit_per_query

        # Log page filter if used
        if page_filter:
            logger.info(f"Page filter active: restricting search to page {page_filter}")

        for query in queries:
            try:
                results = self.weaviate.search_chunks(
                    query=query,
                    process_id=process_id,
                    limit=overfetch_limit,
                    alpha=alpha,  # Dynamic: 0.0 for exploratory (BM25), 0.5 for specific (hybrid)
                    page_filter=page_filter  # Pass page filter to Weaviate
                )

                for result in results:
                    chunk_id = result.get('chunk_id')
                    if chunk_id and chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        all_results.append(result)

            except Exception as e:
                logger.error(f"Search error for query '{query[:50]}': {e}")

        if not all_results:
            return []

        # Sort by Weaviate score first
        all_results.sort(
            key=lambda x: float(x.get('_additional', {}).get('score', 0) or 0),
            reverse=True
        )

        # Apply FlashRank reranking if available
        # SKIP reranking for exploratory queries (alpha=0.0) - BM25 keyword matches are sufficient
        # Cross-encoder reranking can push out keyword matches in favor of semantic similarity
        is_exploratory = alpha == 0.0
        if use_reranking and self.reranker.is_available and len(queries) > 0 and not is_exploratory:
            # Use first query for reranking (the original query)
            # Return 25 chunks for parallel agent processing
            reranked = self.reranker.rerank(
                query=queries[0],
                results=all_results,
                top_k=25  # Get 25 chunks for parallel agents
            )
            logger.debug(f"FlashRank reranked {len(all_results)} results to {len(reranked)}")
            return reranked
        elif is_exploratory:
            logger.info(f"Skipping FlashRank reranking for exploratory query (alpha={alpha})")
            return all_results[:25]  # Return top 25 by BM25 score

        return all_results[:25]  # Return 25 for parallel agents

    # =========================================================================
    # PHASE 6: Neo4j Query Methods
    # =========================================================================

    def _process_structural_query(
        self,
        query: str,
        process_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Process structural queries using Neo4j only.

        Handles:
        - Page finding: "What page has the specifications table?"
        - Table structure: "How many tables are there?"
        - Document overview: "Show document structure"

        Args:
            query: User's structural query
            process_id: Document UUID
            filename: Document filename

        Returns:
            Response dict with structural answer
        """
        if not self.neo4j.is_connected:
            return {
                'answer': "Structural queries require Neo4j, which is not connected.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'structural',
                'error': True
            }

        query_lower = query.lower()
        result_data = []

        try:
            # Try different structural query types
            if 'page' in query_lower and ('table' in query_lower or 'spec' in query_lower):
                # "What page has tables/specifications?"
                cypher, params = self.cypher_templates.find_pages_with_tables(process_id)
                result_data = self.neo4j.query(cypher, params)

            elif 'how many table' in query_lower:
                # "How many tables are there?"
                cypher, params = self.cypher_templates.count_tables_per_page(process_id)
                result_data = self.neo4j.query(cypher, params)

            elif 'structure' in query_lower or 'overview' in query_lower:
                # "Show document structure"
                cypher, params = self.cypher_templates.get_document_structure(process_id)
                result_data = self.neo4j.query(cypher, params)

            elif 'header' in query_lower:
                # "What are the column headers?"
                cypher, params = self.cypher_templates.get_column_headers_from_all_tables(process_id)
                result_data = self.neo4j.query(cypher, params)

            else:
                # Generic statistics
                result_data = [self.neo4j.get_document_statistics(process_id)]

            # Format response
            if result_data:
                # Use LLM to synthesize a natural language answer
                context_str = json.dumps(result_data, indent=2, default=str)
                answer = synthesize_answer_sync(
                    query=query,
                    chunks=[{'content': context_str, 'chunk_type': 'neo4j_structural'}],
                    filename=filename
                )
                return {
                    'answer': answer.get('answer', str(result_data)),
                    'references': [],
                    'confidence': 0.9,
                    'query_type': 'structural',
                    'neo4j_data': result_data,
                    'error': False
                }
            else:
                return {
                    'answer': "No structural information found for this document.",
                    'references': [],
                    'confidence': 0.3,
                    'query_type': 'structural',
                    'error': False
                }

        except Exception as e:
            logger.error(f"Structural query error: {e}")
            return {
                'answer': f"Error processing structural query: {str(e)}",
                'references': [],
                'confidence': 0.0,
                'query_type': 'structural',
                'error': True
            }

    def _process_hybrid_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        query_variations: List[str]
    ) -> Dict[str, Any]:
        """
        Process hybrid semantic-structural queries using Multi-Agent Cypher generation.

        UPGRADED Flow (Phase 7 with Multi-Agent Pipeline):
        1. Multi-Agent service handles full pipeline:
           - Structural Probe (finds WHERE data exists)
           - Hard Constraints (forces correct node type)
           - Logic-First Planning (step-by-step reasoning)
           - Dynamic Cypher Generation
           - NEV Auditor (validates before execution)
        2. Falls back to LangChain if multi-agent fails
        3. Falls back to Weaviate-only as last resort

        Args:
            query: User's query
            process_id: Document UUID
            filename: Document filename
            query_variations: Rephrased query variations

        Returns:
            Response with comprehensive data from all pages
        """
        # =================================================================
        # TRY MULTI-AGENT CYPHER FIRST (Most Advanced)
        # =================================================================
        logger.info("Attempting Multi-Agent Cypher generation...")
        try:
            multiagent_result = run_fewshot_cypher_generation(
                user_query=query,
                process_id=process_id,
                max_iterations=3
            )

            if multiagent_result.get('success') and multiagent_result.get('results'):
                results = multiagent_result['results']
                logger.info(f"Multi-Agent Cypher SUCCESS: {len(results)} results in {multiagent_result.get('iterations', 1)} iterations")

                # USE the natural_answer from Multi-Agent pipeline directly
                # DO NOT call synthesize_answer_sync again - it reinterprets and corrupts the data!
                answer = multiagent_result.get('answer', '')

                # If no answer from pipeline, format results as JSON
                if not answer:
                    answer = f"Found {len(results)} results. See table below for details."

                # Check if export was requested and file was created
                export_path = multiagent_result.get('export_path')
                export_format = multiagent_result.get('export_format')

                # Add export info to answer if file was created
                if export_path and export_format:
                    import os
                    filename = os.path.basename(export_path)
                    export_type = "Excel" if export_format == "excel" else "CSV"
                    answer = f"{answer}\n\n📥 **Data exported to {export_type}:** [Download {filename}](/download/{filename})"

                return {
                    'answer': answer,
                    'references': [],
                    'confidence': 0.95,
                    'query_type': 'hybrid_semantic_structural',
                    'neo4j_rows_extracted': len(results),
                    'dynamic_cypher': True,
                    'method': 'multiagent_cypher',
                    'cypher_used': multiagent_result.get('cypher', ''),
                    'iterations': multiagent_result.get('iterations', 1),
                    'export_path': export_path,
                    'export_format': export_format,
                    'error': False
                }
            else:
                logger.warning(f"Multi-Agent Cypher failed: {multiagent_result.get('error', 'No results')}")

        except Exception as e:
            logger.error(f"Multi-Agent Cypher error: {e}")

        # =================================================================
        # FALLBACK TO LANGCHAIN NEO4J
        # =================================================================
        logger.info("Falling back to LangChain Neo4j...")

        # Check if LangChain Neo4j is connected (preferred) or fall back to raw Neo4j
        use_langchain = self.langchain_neo4j.is_connected

        if not use_langchain and not self.neo4j.is_connected:
            logger.warning("Neither LangChain Neo4j nor raw Neo4j connected, falling back to Weaviate-only")
            return self._process_vector_only_query(
                query, process_id, filename, query_variations
            )

        # =================================================================
        # ECD/MFI SPECIALIZED QUERY DETECTION
        # =================================================================
        # Check if query is asking for ECD concentration data - use pre-built template
        query_lower = query.lower()
        is_ecd_query = (
            ('concentration' in query_lower and 'ecd' in query_lower) or
            ('concentration' in query_lower and 'mfi' in query_lower) or
            ('concentration' in query_lower and 'all pages' in query_lower) or
            ('particle' in query_lower and 'concentration' in query_lower) or
            ('ecd' in query_lower and ('extract' in query_lower or 'all' in query_lower))
        )

        if is_ecd_query and self.neo4j.is_connected:
            logger.info("ECD concentration query detected - using specialized pivoted template")
            try:
                # Use our pre-built ECD concentration pivoted query
                cypher, params = self.cypher_templates.extract_ecd_concentration_pivoted(process_id)
                results = self.neo4j.query(cypher, params)

                if results:
                    logger.info(f"ECD pivoted query returned {len(results)} rows")

                    # Format results as a nice table
                    table_lines = ["ECD Concentration Data (particles/mL) by threshold:", ""]
                    table_lines.append("Page     >=1.00       >=2.00       >=5.00       >=10.00      >=25.00      >=50.00")
                    table_lines.append("-" * 85)

                    for row in results:
                        page = str(row.get('page', '')).ljust(8)
                        c1 = str(row.get('>=1.00') or row.get('col1') or '-').ljust(12)
                        c2 = str(row.get('>=2.00') or row.get('col2') or '-').ljust(12)
                        c5 = str(row.get('>=5.00') or row.get('col5') or '-').ljust(12)
                        c10 = str(row.get('>=10.00') or row.get('col10') or '-').ljust(12)
                        c25 = str(row.get('>=25.00') or row.get('col25') or '-').ljust(12)
                        c50 = str(row.get('>=50.00') or row.get('col50') or '-').ljust(12)
                        table_lines.append(f"{page}{c1}{c2}{c5}{c10}{c25}{c50}")

                    table_lines.append("-" * 85)
                    table_lines.append(f"Total: {len(results)} ECD tables found across document")

                    return {
                        'answer': "\n".join(table_lines),
                        'references': [],
                        'confidence': 0.95,
                        'query_type': 'ecd_concentration_extraction',
                        'neo4j_rows_extracted': len(results),
                        'dynamic_cypher': False,
                        'template_used': 'extract_ecd_concentration_pivoted',
                        'error': False
                    }
            except Exception as e:
                logger.error(f"ECD template query failed: {e}, falling back to dynamic Cypher")
        # =================================================================

        try:
            # Step 1: Weaviate search to find relevant chunks and identify patterns
            weaviate_chunks = self._parallel_search(
                queries=query_variations,
                process_id=process_id,
                limit_per_query=5
            )

            if not weaviate_chunks:
                return {
                    'answer': "No relevant data found in the document.",
                    'references': [],
                    'confidence': 0.0,
                    'query_type': 'hybrid_semantic_structural',
                    'error': False
                }

            # Step 2: Use LangChain Neo4j for DYNAMIC Cypher generation with retry and fallback
            if use_langchain:
                logger.info("Using LangChain Neo4j for dynamic Cypher generation (with retry + fallback)")

                # Execute hybrid query with Weaviate context, retry, and template fallback
                neo4j_result = self.langchain_neo4j.query_with_context_and_fallback(
                    question=query,
                    process_id=process_id,
                    weaviate_chunks=weaviate_chunks,
                    cypher_templates=self.cypher_templates  # Pass templates for fallback
                )

                if neo4j_result.get('success') and neo4j_result.get('results'):
                    all_column_data = neo4j_result['results']
                    method = neo4j_result.get('method', 'unknown')
                    retries = neo4j_result.get('retries_used', 0)
                    logger.info(f"LangChain Neo4j returned {len(all_column_data)} results (method={method}, retries={retries})")
                    logger.info(f"Generated Cypher: {neo4j_result.get('cypher', 'N/A')[:200]}...")
                else:
                    logger.info(f"LangChain Neo4j query failed or empty: {neo4j_result.get('error', 'No results')}")
                    all_column_data = []

            else:
                # Fallback to old template-based approach
                logger.info("Falling back to template-based Cypher (LangChain not available)")
                header_patterns = self._extract_header_patterns(query, weaviate_chunks)
                logger.info(f"Extracted header patterns: {header_patterns}")

                all_column_data = []
                for pattern in header_patterns[:3]:
                    cypher, params = self.cypher_templates.extract_column_by_header(
                        process_id, pattern
                    )
                    results = self.neo4j.query(cypher, params)
                    if results:
                        all_column_data.extend(results)

            # Step 3: If we got Neo4j data, synthesize answer from it
            if all_column_data:
                # Format Neo4j results for synthesis
                neo4j_context = self._format_neo4j_results_for_synthesis(all_column_data)

                answer_data = synthesize_answer_sync(
                    query=query,
                    chunks=[{
                        'content': neo4j_context,
                        'chunk_type': 'neo4j_extraction',
                        'page': all_column_data[0].get('page', 1) if isinstance(all_column_data[0], dict) else 1
                    }],
                    filename=filename
                )

                # Build references from Neo4j bbox data
                references = []
                for item in all_column_data[:10]:  # Limit references
                    if isinstance(item, dict) and item.get('bbox'):
                        bbox = item['bbox']
                        if isinstance(bbox, dict):
                            references.append({
                                'page': item.get('page', 1),
                                'bbox': {
                                    'left': bbox.get('left', 0),
                                    'top': bbox.get('top', 0),
                                    'width': bbox.get('right', 0) - bbox.get('left', 0),
                                    'height': bbox.get('bottom', 0) - bbox.get('top', 0)
                                },
                                'cell_id': item.get('cell_key', ''),
                                'text': item.get('value', str(item.get('text', '')))
                            })

                return {
                    'answer': answer_data.get('answer', ''),
                    'references': references,
                    'confidence': answer_data.get('confidence', 0.85),
                    'query_type': 'hybrid_semantic_structural',
                    'neo4j_rows_extracted': len(all_column_data),
                    'dynamic_cypher': use_langchain,
                    'error': False
                }
            else:
                # Fall back to Weaviate-only response
                logger.info("No Neo4j data found, falling back to Weaviate chunks")
                return self._process_vector_only_query(
                    query, process_id, filename, query_variations
                )

        except Exception as e:
            logger.error(f"Hybrid query error: {e}")
            # Fall back to Weaviate-only on error
            return self._process_vector_only_query(
                query, process_id, filename, query_variations
            )

    def _process_extraction_query(
        self,
        query: str,
        process_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Process extraction queries - export ALL data from tables.

        Handles:
        - "Export all test results to Excel"
        - "Give me ALL rows from the specifications table"

        Args:
            query: User's extraction query
            process_id: Document UUID
            filename: Document filename

        Returns:
            Response with complete table data
        """
        if not self.neo4j.is_connected:
            return {
                'answer': "Extraction queries require Neo4j, which is not connected.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'extraction',
                'error': True
            }

        try:
            # Get document statistics first
            stats = self.neo4j.get_document_statistics(process_id)

            if not stats or stats.get('table_count', 0) == 0:
                return {
                    'answer': "No tables found in this document for extraction.",
                    'references': [],
                    'confidence': 0.5,
                    'query_type': 'extraction',
                    'error': False
                }

            # Get all pages with tables
            cypher, params = self.cypher_templates.find_pages_with_tables(process_id)
            pages_with_tables = self.neo4j.query(cypher, params)

            # Extract all table data
            all_tables_data = []
            for page_info in pages_with_tables:
                for chunk_index in page_info.get('chunk_indices', []):
                    table_data = self.neo4j.get_full_table_data_by_chunk_index(
                        process_id, chunk_index
                    )
                    if table_data:
                        all_tables_data.append(table_data)

            if all_tables_data:
                # Format for response
                extraction_summary = f"Extracted {len(all_tables_data)} table(s) with {sum(t.get('row_count', 0) for t in all_tables_data)} total rows.\n\n"

                # Create markdown summary of tables
                for i, table in enumerate(all_tables_data, 1):
                    extraction_summary += f"**Table {i}** (Page {table.get('page_num', '?')}):\n"
                    extraction_summary += f"- Columns: {', '.join(table.get('headers', []))}\n"
                    extraction_summary += f"- Rows: {table.get('row_count', 0)}\n\n"

                return {
                    'answer': extraction_summary,
                    'references': [],
                    'confidence': 0.95,
                    'query_type': 'extraction',
                    'extracted_tables': all_tables_data,
                    'table_count': len(all_tables_data),
                    'total_rows': sum(t.get('row_count', 0) for t in all_tables_data),
                    'error': False
                }
            else:
                return {
                    'answer': "Could not extract table data from this document.",
                    'references': [],
                    'confidence': 0.3,
                    'query_type': 'extraction',
                    'error': False
                }

        except Exception as e:
            logger.error(f"Extraction query error: {e}")
            return {
                'answer': f"Error extracting data: {str(e)}",
                'references': [],
                'confidence': 0.0,
                'query_type': 'extraction',
                'error': True
            }

    def _process_visual_audit_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        precomputed_discovery: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process visual audit queries using Gemini multimodal.

        Phase 7: Two-stage process with LLM-based auto-detection:
        - Stage 1: Discovery (BM25/Hybrid search + LLM to find specific identifiers)
        - Stage 2: Deep Analysis (Gemini with image + OCR text)

        Auto-analyze logic:
        - If user mentions specific identifier (e.g., "step 7.3") and found on 1 page → auto-analyze
        - If found on multiple pages → show only those pages for user selection
        - If general query → show all discovered pages for selection

        Args:
            query: User's audit query
            process_id: Document UUID
            filename: Document filename
            precomputed_discovery: Pre-computed discovery result from streaming endpoint (avoids duplicate discovery)

        Returns:
            Response dict with discovery results or audit analysis
        """
        try:
            # Stage 1: Discovery - use precomputed if available, otherwise discover
            if precomputed_discovery and precomputed_discovery.get('success'):
                discovery_result = precomputed_discovery
                logger.info(f"Using precomputed discovery: pages={discovery_result.get('pages_found', [])}, auto_analyze={discovery_result.get('auto_analyze')}")
            else:
                discovery_result = self.visual_audit.discover_audit_targets(
                    query=query,
                    process_id=process_id,
                    filename=filename
                )

            if not discovery_result.get('success'):
                return {
                    'answer': discovery_result.get('message', 'No relevant data found for audit.'),
                    'references': [],
                    'confidence': 0.3,
                    'query_type': 'visual_audit',
                    'stage': 'discovery',
                    'error': False
                }

            chunks = discovery_result.get('chunks', [])

            # =================================================================
            # AUTO-ANALYZE: If specific identifier found on single page
            # =================================================================
            if discovery_result.get('auto_analyze') and discovery_result.get('auto_analyze_page'):
                page_to_analyze = discovery_result['auto_analyze_page']
                identifier = discovery_result.get('identifier', '')
                identifier_type = discovery_result.get('identifier_type', '')

                logger.info(f"Auto-analyzing: {identifier_type} '{identifier}' on page {page_to_analyze}")

                # Construct PDF path from filename - use ABSOLUTE path to backend/temp/
                import os
                import re
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                temp_dir = os.path.join(backend_dir, 'temp')

                # Try multiple path patterns to find the PDF
                pdf_path = None
                search_paths = [
                    # Original filename (most common)
                    os.path.join(temp_dir, filename),
                    # Filename with spaces replaced
                    os.path.join(temp_dir, filename.replace(' ', '_')),
                ]

                # Also try sanitized version
                sanitized = filename.replace('.pdf', '').replace('.PDF', '')
                sanitized = sanitized.replace(' ', '_').replace('(', '').replace(')', '')
                sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', sanitized)
                sanitized = re.sub(r'_+', '_', sanitized).rstrip('_')
                search_paths.append(os.path.join(temp_dir, f"{sanitized}.pdf"))

                # Log search paths for debugging
                logger.info(f"Searching for PDF in paths: {search_paths}")

                for path in search_paths:
                    if os.path.exists(path):
                        pdf_path = path
                        logger.info(f"Found PDF at: {pdf_path}")
                        break

                if not pdf_path:
                    # Last resort: search temp dir for any PDF with similar name
                    if os.path.exists(temp_dir):
                        for f in os.listdir(temp_dir):
                            if f.endswith('.pdf') and (filename.replace('.pdf', '') in f or sanitized in f):
                                pdf_path = os.path.join(temp_dir, f)
                                logger.info(f"Found PDF via search: {pdf_path}")
                                break

                if pdf_path and os.path.exists(pdf_path):
                    # Proceed directly to Stage 2 deep analysis
                    deep_result = self._process_visual_audit_deep_analysis(
                        query=query,
                        process_id=process_id,
                        pdf_path=pdf_path,
                        page_numbers=[page_to_analyze],
                        chunks=chunks
                    )

                    # Add context about auto-detection to the answer
                    if deep_result.get('answer'):
                        prefix = f"**Auto-detected {identifier_type} {identifier} on Page {page_to_analyze}**\n\n"
                        deep_result['answer'] = prefix + deep_result['answer']

                    return deep_result
                else:
                    logger.warning(f"PDF not found for auto-analyze. Searched: {search_paths}")
                    logger.warning(f"Temp dir contents: {os.listdir(temp_dir) if os.path.exists(temp_dir) else 'DIR NOT FOUND'}")
                    # Return explicit error instead of silent fallthrough
                    return {
                        'answer': f"**Visual Audit Error**: Could not find PDF file for page {page_to_analyze}.\n\nPlease re-upload the document or check if the file exists.",
                        'references': [],
                        'confidence': 0.0,
                        'query_type': 'visual_audit',
                        'error': True
                    }

            # =================================================================
            # MANUAL SELECTION: Build response with page options
            # =================================================================
            # Build references from parallel agent findings (with bbox data)
            # Each finding from discovery agents has bbox from the source chunk
            references = []
            findings = discovery_result.get('findings', [])

            if findings:
                # Use findings from parallel agents (have bbox from chunks)
                for finding in findings[:20]:  # Limit to 20 references
                    bbox = finding.get('bbox', {})
                    if bbox and (bbox.get('left') or bbox.get('top')):
                        references.append({
                            'page': finding.get('page', 1),
                            'bbox': {
                                'left': bbox.get('left', 0),
                                'top': bbox.get('top', 0),
                                'width': bbox.get('right', 0) - bbox.get('left', 0),
                                'height': bbox.get('bottom', 0) - bbox.get('top', 0)
                            },
                            'text': finding.get('summary', '')[:100],
                            'audit_type': finding.get('audit_type', 'general'),
                            'relevance': finding.get('relevance', 0)
                        })
            else:
                # Fallback: use raw chunks if no findings
                for chunk in chunks[:20]:
                    if chunk.get('bbox_left') is not None:
                        references.append({
                            'page': chunk.get('page', 1),
                            'bbox': {
                                'left': chunk.get('bbox_left', 0),
                                'top': chunk.get('bbox_top', 0),
                                'width': (chunk.get('bbox_right', 0) - chunk.get('bbox_left', 0)),
                                'height': (chunk.get('bbox_bottom', 0) - chunk.get('bbox_top', 0))
                            },
                            'text': chunk.get('content', '')[:100]
                        })

            return {
                'answer': discovery_result.get('message', ''),
                'references': references,
                'confidence': 0.8,
                'query_type': 'visual_audit',
                'stage': 'discovery',
                'needs_page_selection': discovery_result.get('needs_page_selection', True),
                'pages_found': discovery_result.get('pages_found', []),
                'findings': findings,  # Include findings for UI display
                'identifier': discovery_result.get('identifier'),
                'identifier_type': discovery_result.get('identifier_type'),
                'chunks': chunks,  # Pass chunks for Stage 2
                'error': False
            }

        except Exception as e:
            logger.error(f"Visual audit query error: {e}")
            return {
                'answer': f"Error processing visual audit: {str(e)}",
                'references': [],
                'confidence': 0.0,
                'query_type': 'visual_audit',
                'error': True
            }

    def _process_visual_audit_deep_analysis(
        self,
        query: str,
        process_id: str,
        pdf_path: str,
        page_numbers: List[int],
        chunks: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process visual audit Stage 2: Deep analysis with Gemini.

        Called when user specifies which page(s) to analyze.

        Args:
            query: Original audit query
            process_id: Document UUID
            pdf_path: Path to PDF file
            page_numbers: Pages to analyze (max 3)
            chunks: Pre-fetched chunks from Stage 1

        Returns:
            Response dict with detailed audit analysis
        """
        try:
            if len(page_numbers) == 1:
                # Single page analysis
                result = self.visual_audit.deep_analyze_page(
                    query=query,
                    process_id=process_id,
                    pdf_path=pdf_path,
                    page_number=page_numbers[0],
                    chunks=chunks
                )
            else:
                # Multi-page analysis (parallel)
                result = self.visual_audit.deep_analyze_multiple_pages(
                    query=query,
                    process_id=process_id,
                    pdf_path=pdf_path,
                    page_numbers=page_numbers,
                    chunks=chunks
                )

            if result.get('success'):
                # Extract cell references from Gemini's analysis
                # Gemini returns [cell:CHUNK:CELL_ID|TYPE] references (TYPE: error/info)
                import re
                analysis_text = result.get('analysis', '')

                # Log raw analysis for debugging highlight_type extraction
                logger.info(f"[Visual Audit] Raw analysis text (first 500 chars): {analysis_text[:500]}")

                # Updated regex to capture optional |type suffix
                cell_refs = re.findall(r'\[cell:(\d+):([^|\]]+)(?:\|([a-z]+))?\]', analysis_text)
                logger.info(f"[Visual Audit] Extracted cell_refs: {cell_refs}")

                # Use page_chunks returned from visual_audit service (the actual chunks Gemini used)
                used_chunks = result.get('page_chunks', []) or chunks or []

                # Build grounding map from chunks' cell_grounding
                grounding_map = {}
                for chunk in used_chunks:
                    chunk_index = chunk.get('chunk_index', 0)
                    chunk_page = chunk.get('page', 1)
                    if chunk.get('cell_grounding'):
                        try:
                            cg = json.loads(chunk['cell_grounding'])
                            for cell_id, data in cg.items():
                                key = f"{chunk_index}:{cell_id}"
                                grounding_map[key] = {
                                    'page': chunk_page,
                                    'bbox': data.get('bbox', {}),
                                    'text': data.get('text', ''),
                                    'row': data.get('row'),
                                    'col': data.get('col')
                                }
                        except:
                            pass

                # Build references from cell_refs found in Gemini's response
                # First pass: collect all refs, prioritizing 'error' over 'info' for same cell
                ref_map = {}  # key -> (data, highlight_type)
                for match in cell_refs:
                    chunk_idx = match[0]
                    cell_id = match[1]
                    highlight_type = match[2] if len(match) > 2 and match[2] else 'info'
                    key = f"{chunk_idx}:{cell_id}"
                    if key in grounding_map:
                        # If already seen, only update if new one is 'error' (error takes priority)
                        if key in ref_map:
                            if highlight_type == 'error':
                                ref_map[key] = (grounding_map[key], 'error')
                        else:
                            ref_map[key] = (grounding_map[key], highlight_type)

                # Build references list from deduplicated map
                references = []
                for key, (data, highlight_type) in ref_map.items():
                    bbox = data.get('bbox', {})
                    if bbox:
                        references.append({
                            'page': data.get('page', page_numbers[0]),
                            'bbox': {
                                'left': bbox.get('left', 0),
                                'top': bbox.get('top', 0),
                                'width': bbox.get('width', 0),
                                'height': bbox.get('height', 0)
                            },
                            'cell_id': key,
                            'text': data.get('text', '')[:100],
                            'type': 'cell',
                            'highlight_type': highlight_type
                        })

                logger.info(f"[Visual Audit] Final references with types: {[(r['cell_id'], r['highlight_type']) for r in references]}")

                logger.info(f"Visual audit extracted {len(references)} cell references from analysis")

                # FALLBACK: If Gemini didn't return cell references, use the chunks' cell_grounding
                # Use the same chunks that Gemini used for analysis (returned from visual_audit service)
                if not references and used_chunks:
                    logger.info(f"No cell refs from Gemini - extracting references from {len(used_chunks)} used chunks")
                    for chunk in used_chunks:
                        chunk_page = chunk.get('page', page_numbers[0] if page_numbers else 1)
                        chunk_index = chunk.get('chunk_index', 0)

                        # Extract from cell_grounding (has bbox for each cell)
                        if chunk.get('cell_grounding'):
                            try:
                                cg = json.loads(chunk['cell_grounding'])
                                for cell_id, cell_data in list(cg.items())[:5]:  # Top 5 cells per chunk
                                    cell_bbox = cell_data.get('bbox', {})
                                    if cell_bbox and (cell_bbox.get('left') or cell_bbox.get('top')):
                                        references.append({
                                            'page': chunk_page,
                                            'bbox': {
                                                'left': cell_bbox.get('left', 0),
                                                'top': cell_bbox.get('top', 0),
                                                'width': cell_bbox.get('width', 0),
                                                'height': cell_bbox.get('height', 0)
                                            },
                                            'cell_id': f"{chunk_index}:{cell_id}",
                                            'text': cell_data.get('text', '')[:100],
                                            'type': 'cell'
                                        })
                            except:
                                pass

                        # Fallback to chunk-level bbox if no cell_grounding
                        if not chunk.get('cell_grounding'):
                            bbox_left = chunk.get('bbox_left')
                            bbox_top = chunk.get('bbox_top')
                            if bbox_left is not None and bbox_top is not None:
                                references.append({
                                    'page': chunk_page,
                                    'bbox': {
                                        'left': bbox_left,
                                        'top': bbox_top,
                                        'width': (chunk.get('bbox_right', bbox_left) - bbox_left),
                                        'height': (chunk.get('bbox_bottom', bbox_top) - bbox_top)
                                    },
                                    'chunk_index': chunk_index,
                                    'text': chunk.get('content', '')[:100],
                                    'type': 'chunk'
                                })

                    # Limit references for UI performance
                    references = references[:20]
                    logger.info(f"Extracted {len(references)} references from used chunks")

                return {
                    'answer': result.get('analysis', ''),
                    'references': references,
                    'confidence': 0.9,
                    'query_type': 'visual_audit',
                    'stage': 'deep_analysis',
                    'pages_analyzed': result.get('pages_analyzed', page_numbers),
                    'error': False
                }
            else:
                return {
                    'answer': f"Visual analysis failed: {result.get('error', 'Unknown error')}",
                    'references': [],
                    'confidence': 0.0,
                    'query_type': 'visual_audit',
                    'stage': 'deep_analysis',
                    'error': True
                }

        except Exception as e:
            logger.error(f"Visual audit deep analysis error: {e}")
            return {
                'answer': f"Error in visual analysis: {str(e)}",
                'references': [],
                'confidence': 0.0,
                'query_type': 'visual_audit',
                'error': True
            }

    # =========================================================================
    # PHASE 8: New Intent Handlers (Precision, Exhaustive, Comparison)
    # =========================================================================

    def _process_precision_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """
        Process precision queries - fast path for single value lookups.

        Uses single agent (no parallel overhead) for queries like:
        - "What is the batch number?"
        - "When was this signed?"
        - "What is the pH value?"

        Args:
            query: User's query
            process_id: Document UUID
            filename: Document filename
            plan: ExecutionPlan with search parameters

        Returns:
            Response dict with answer and references
        """
        logger.info(f"PRECISION query: bm25={plan.bm25_limit}, vec={plan.vector_limit}, rerank={plan.rerank_limit}, alpha={plan.alpha}")

        # Dual-alpha search: hybrid + pure BM25 for better recall on word variations
        # Hybrid pass catches semantic matches, BM25 pass catches keyword matches
        hybrid_chunks = self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=plan.alpha,
            page_filter=plan.page_filter
        )

        bm25_chunks = self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=0.0,  # Pure BM25 to catch keyword variations
            page_filter=plan.page_filter
        )

        # Merge results: BM25 first (better for exact/partial keyword matches),
        # then hybrid (catches semantic matches BM25 missed), deduplicate
        seen_ids = set()
        chunks = []
        for chunk in bm25_chunks + hybrid_chunks:
            cid = chunk.get('chunk_id', id(chunk))
            if cid not in seen_ids:
                seen_ids.add(cid)
                chunks.append(chunk)

        if not chunks:
            return {
                'answer': "I couldn't find the requested information in the document.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'precision',
                'intent': plan.intent.value,
                'error': False
            }

        # Rerank merged results with FlashRank MiniLM-L-12 (handles large table chunks)
        if self.reranker and self.reranker.is_available:
            chunks = self.reranker.rerank(query, chunks, top_k=plan.rerank_limit)
        else:
            chunks = chunks[:plan.rerank_limit]

        # SINGLE AGENT - no parallel overhead
        answer_data = synthesize_answer_sync(
            query=query,
            chunks=chunks[:10],  # Allow more chunks for precision (large tables need more context)
            filename=filename
        )

        # Extract references
        response = build_response_with_references(
            answer_data=answer_data,
            chunks=chunks,
            query_type='precision'
        )

        response['intent'] = plan.intent.value
        response['agent_strategy'] = plan.agent_strategy.value
        response['latency_optimized'] = True

        return response

    def _process_exhaustive_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        plan: ExecutionPlan,
        recent_messages: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process exhaustive queries - extract ALL instances across document + Final Synthesis.

        Phase 8 Enhancement: Query-Focused Multi-Agent with Final Synthesis
        1. Query Analyzer extracts target terms for exhaustive extraction
        2. Parallel agents process chunks for ALL instances
        3. Final Synthesis Agent deduplicates and formats complete list

        Uses 8 parallel agents for maximum recall on queries like:
        - "List ALL batch numbers"
        - "Show every test result"
        - "Extract all concentration values"

        Args:
            query: User's query
            process_id: Document UUID
            filename: Document filename
            plan: ExecutionPlan with search parameters
            recent_messages: Recent conversation for context resolution

        Returns:
            Response dict with comprehensive data
        """
        logger.info(f"EXHAUSTIVE query: bm25={plan.bm25_limit}, vec={plan.vector_limit}, rerank={plan.rerank_limit}, alpha={plan.alpha}")

        # Search for relevant chunks
        chunks = self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=plan.alpha,
            page_filter=plan.page_filter
        )

        if not chunks:
            return {
                'answer': "I couldn't find any instances of the requested data in the document.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'exhaustive',
                'intent': plan.intent.value,
                'error': False
            }

        # Rerank chunks
        if self.reranker.is_available:
            chunks = self.reranker.rerank(query, chunks, top_k=plan.rerank_limit)
        else:
            chunks = chunks[:plan.rerank_limit]

        logger.info(f"Exhaustive search: {len(chunks)} chunks after reranking")

        # Use parallel agents for maximum coverage
        result = run_parallel_agents_sync(
            query=query,
            chunks=chunks,
            filename=filename
        )

        # Use agent result directly
        answer = result.get('answer', '')
        confidence = result.get('confidence', 0.7)
        cell_ids = result.get('cell_ids', [])

        return {
            'answer': answer,
            'references': format_references_for_frontend(result.get('references', [])),
            'confidence': confidence,
            'query_type': 'exhaustive',
            'intent': plan.intent.value,
            'agent_strategy': plan.agent_strategy.value,
            'chunks_used': len(chunks),
            'agents_used': result.get('agents_used', 5),
            'cell_ids': cell_ids,
            'error': False
        }

    # =========================================================================
    # CROSS-REFERENCE HANDLER (Phase 9)
    # =========================================================================

    def _process_cross_reference_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        plan: ExecutionPlan,
        recent_messages: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process cross-reference queries that require two-step locate + extract.

        Handles ambiguous multi-page queries like:
        - "Find all test data where batch number 12345 is present"
        - "Show specifications on pages that have product ABC"

        Phase A: Decompose query into locate + extract sub-queries
        Phase B: LOCATE - find pages matching the locating criterion
        Phase C: EXTRACT - search for desired data on discovered pages
        Phase D: Deduplicate + rerank combined results
        Phase E: Parallel agents synthesize final answer
        """
        logger.info(f"CROSS_REFERENCE query: bm25={plan.bm25_limit}, vec={plan.vector_limit}, "
                     f"rerank={plan.rerank_limit}, alpha={plan.alpha}")

        # Phase A: Get sub-queries from plan or decompose via LLM
        locate_query = None
        extract_query = None

        if plan.sub_queries and len(plan.sub_queries) >= 2:
            for sq in plan.sub_queries:
                if sq.get("step") == "locate":
                    locate_query = sq.get("query", "")
                elif sq.get("step") == "extract":
                    extract_query = sq.get("query", "")
            logger.info(f"Sub-queries from classifier - locate: '{locate_query}', extract: '{extract_query}'")

        if not locate_query or not extract_query:
            # Fallback: use LLM to decompose the query
            logger.info("Sub-queries not provided, decomposing via LLM")
            decomposed = self._decompose_cross_reference_query(query)
            if decomposed:
                locate_query = decomposed.get("locate_query", "")
                extract_query = decomposed.get("extract_query", "")
                logger.info(f"LLM decomposed - locate: '{locate_query}', extract: '{extract_query}'")

        if not locate_query or not extract_query:
            # Final fallback: treat as exhaustive
            logger.warning("Cross-reference decomposition failed, falling back to exhaustive")
            return self._process_exhaustive_query(query, process_id, filename, plan, recent_messages)

        # Phase B: LOCATE - find pages where the locating criterion exists
        logger.info(f"Phase B: LOCATE step - searching for '{locate_query}'")
        locate_chunks = self.weaviate.search_chunks(
            query=locate_query,
            process_id=process_id,
            limit=20,
            alpha=0.3,  # Favor BM25 for exact matching of identifiers
            page_filter=plan.page_filter
        )

        if not locate_chunks:
            return {
                'answer': f"I searched for \"{locate_query}\" but couldn't find it in the document. "
                          f"Please verify the identifier or try a different search term.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'cross_reference',
                'intent': plan.intent.value,
                'error': False
            }

        # Extract unique pages from locate results, preserving score order
        seen_pages = set()
        discovered_pages = []
        for chunk in locate_chunks:
            page = chunk.get('page')
            if page and page not in seen_pages:
                seen_pages.add(page)
                discovered_pages.append(page)

        # Cap at 20 pages for better recall on large documents
        if len(discovered_pages) > 20:
            logger.warning(f"Cross-reference found {len(discovered_pages)} pages, capping at top 20")
            discovered_pages = discovered_pages[:20]

        logger.info(f"LOCATE found {len(discovered_pages)} pages: {discovered_pages}")

        # Phase C: EXTRACT - search for desired data on each discovered page
        logger.info(f"Phase C: EXTRACT step - searching for '{extract_query}' on pages {discovered_pages}")
        all_extract_chunks = []
        chunks_per_page = max(plan.bm25_limit // len(discovered_pages), 5)

        for page_num in discovered_pages:
            page_chunks = self.weaviate.search_chunks(
                query=extract_query,
                process_id=process_id,
                limit=chunks_per_page,
                alpha=0.5,  # Balanced for extraction
                page_filter=page_num
            )
            all_extract_chunks.extend(page_chunks)
            logger.debug(f"Page {page_num}: {len(page_chunks)} chunks")

        if not all_extract_chunks:
            return {
                'answer': f"I found \"{locate_query}\" on pages {discovered_pages}, "
                          f"but could not find \"{extract_query}\" on those pages.",
                'references': [],
                'confidence': 0.3,
                'query_type': 'cross_reference',
                'intent': plan.intent.value,
                'discovered_pages': discovered_pages,
                'error': False
            }

        # Phase D: Deduplicate by chunk_id + rerank using full original query
        seen_ids = set()
        unique_chunks = []
        for chunk in all_extract_chunks:
            cid = chunk.get('chunk_id', id(chunk))
            if cid not in seen_ids:
                seen_ids.add(cid)
                unique_chunks.append(chunk)

        logger.info(f"EXTRACT collected {len(all_extract_chunks)} chunks, {len(unique_chunks)} unique")

        if self.reranker and self.reranker.is_available:
            chunks = self.reranker.rerank(query, unique_chunks, top_k=plan.rerank_limit)
        else:
            chunks = unique_chunks[:plan.rerank_limit]

        logger.info(f"After reranking: {len(chunks)} chunks for synthesis")

        # Phase E: Parallel agent synthesis
        result = run_parallel_agents_sync(
            query=query,
            chunks=chunks,
            filename=filename,
            max_agents=8,
            focus_entities=plan.search_keywords
        )

        answer = result.get('answer', '')
        confidence = result.get('confidence', 0.7)
        cell_ids = result.get('cell_ids', [])

        return {
            'answer': answer,
            'references': format_references_for_frontend(result.get('references', [])),
            'confidence': confidence,
            'query_type': 'cross_reference',
            'intent': plan.intent.value,
            'agent_strategy': plan.agent_strategy.value,
            'chunks_used': len(chunks),
            'agents_used': result.get('agents_used', 8),
            'cell_ids': cell_ids,
            'discovered_pages': discovered_pages,
            'locate_query': locate_query,
            'extract_query': extract_query,
            'error': False
        }

    def _decompose_cross_reference_query(self, query: str) -> Optional[Dict[str, str]]:
        """
        Fallback LLM call to decompose a cross-reference query into locate + extract parts.
        Used when the intent classifier didn't provide sub_queries.
        """
        try:
            iliad_url = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
            iliad_key = os.getenv("ILIAD_API_KEY", "IHnmjp7BE3ijTUzqnaAHAMK7elgQVZYs")

            prompt = (
                "Given a complex query that requires finding data in one location "
                "and extracting different data from that location, decompose it into two parts.\n\n"
                f"Query: {query}\n\n"
                "Return ONLY JSON:\n"
                '{"locate_query": "<criterion to find relevant pages>", '
                '"extract_query": "<data to extract from those pages>"}'
            )

            headers = {
                "Content-Type": "application/json",
                "x-api-key": iliad_key
            }
            payload = {
                "model": "gemini-2.5-flash",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.0
            }

            response = requests.post(
                f"{iliad_url}/api/llm/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Decomposition LLM error: {response.status_code}")
                return None

            content = response.json()["choices"][0]["message"]["content"]
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())

        except Exception as e:
            logger.error(f"Cross-reference decomposition failed: {e}")
            return None

    def _process_comparison_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """
        Process comparison queries - compare two or more items.

        Uses dual-path search for queries like:
        - "Compare batch 123 vs batch 456"
        - "What's the difference between test A and B?"

        Args:
            query: User's query
            process_id: Document UUID
            filename: Document filename
            plan: ExecutionPlan with comparison_targets

        Returns:
            Response dict with comparison analysis
        """
        targets = plan.comparison_targets or []

        if len(targets) < 2:
            # Fallback to exploratory if we couldn't extract targets
            logger.warning("Comparison query but <2 targets, falling back to exploratory")
            return self._process_exploratory_query(query, process_id, filename, plan)

        logger.info(f"COMPARISON query: targets={targets}, bm25={plan.bm25_limit}, alpha={plan.alpha}")

        # Dual-path search: search for each target separately
        all_chunks = []
        chunks_per_target = plan.bm25_limit // len(targets)

        for target in targets:
            target_chunks = self.weaviate.search_chunks(
                query=target,
                process_id=process_id,
                limit=chunks_per_target,
                alpha=plan.alpha,
                page_filter=plan.page_filter
            )

            # Tag chunks with their comparison target
            for chunk in target_chunks:
                chunk['comparison_target'] = target

            all_chunks.extend(target_chunks)

        if not all_chunks:
            return {
                'answer': f"I couldn't find information about {' or '.join(targets)} in the document.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'comparison',
                'intent': plan.intent.value,
                'error': False
            }

        # Rerank combined results
        if self.reranker.is_available:
            all_chunks = self.reranker.rerank(query, all_chunks, top_k=plan.rerank_limit)
        else:
            all_chunks = all_chunks[:plan.rerank_limit]

        # Synthesize comparison answer
        answer_data = self._synthesize_comparison_answer(
            query=query,
            chunks=all_chunks,
            targets=targets,
            filename=filename
        )

        response = build_response_with_references(
            answer_data=answer_data,
            chunks=all_chunks,
            query_type='comparison'
        )

        response['intent'] = plan.intent.value
        response['agent_strategy'] = plan.agent_strategy.value
        response['compared_items'] = targets

        return response

    def _process_exploratory_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        plan: ExecutionPlan,
        recent_messages: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process exploratory queries - general Q&A with parallel agents.

        Uses parallel agents for queries like:
        - "Tell me about the test results"
        - "What specifications are listed?"
        - "What is the step in page 71?"

        Args:
            query: User's query
            process_id: Document UUID
            filename: Document filename
            plan: ExecutionPlan with search parameters
            recent_messages: Recent conversation for context resolution

        Returns:
            Response dict with answer
        """
        logger.info(f"EXPLORATORY query: bm25={plan.bm25_limit}, vec={plan.vector_limit}, rerank={plan.rerank_limit}, alpha={plan.alpha}")

        # Search for relevant chunks
        chunks = self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=plan.alpha,
            page_filter=plan.page_filter
        )

        if not chunks:
            return {
                'answer': "I couldn't find relevant information in the document.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'exploratory',
                'intent': plan.intent.value,
                'error': False
            }

        # Rerank chunks
        if self.reranker.is_available:
            chunks = self.reranker.rerank(query, chunks, top_k=plan.rerank_limit)
        else:
            chunks = chunks[:plan.rerank_limit]

        # Use parallel agents
        result = run_parallel_agents_sync(
            query=query,
            chunks=chunks,
            filename=filename
        )

        # Use agent result directly
        answer = result.get('answer', '')
        confidence = result.get('confidence', 0.5)
        cell_ids = result.get('cell_ids', [])

        return {
            'answer': answer,
            'references': format_references_for_frontend(result.get('references', [])),
            'confidence': confidence,
            'query_type': 'exploratory',
            'intent': plan.intent.value,
            'agent_strategy': plan.agent_strategy.value,
            'agents_used': result.get('agents_used', 5),
            'cell_ids': cell_ids,
            'error': False
        }

    def _synthesize_comparison_answer(
        self,
        query: str,
        chunks: List[Dict],
        targets: List[str],
        filename: str
    ) -> Dict[str, Any]:
        """
        Synthesize a comparison answer from chunks tagged with comparison targets.

        Args:
            query: Original comparison query
            chunks: Chunks with 'comparison_target' tags
            targets: Items being compared
            filename: Document filename

        Returns:
            Answer data with comparison analysis
        """
        # Group chunks by target
        by_target = {}
        for chunk in chunks:
            target = chunk.get('comparison_target', 'unknown')
            if target not in by_target:
                by_target[target] = []
            by_target[target].append(chunk)

        # Build comparison context
        comparison_context = f"COMPARISON REQUEST: {query}\n\n"
        comparison_context += f"Items to compare: {', '.join(targets)}\n\n"

        for target, target_chunks in by_target.items():
            comparison_context += f"--- {target.upper()} ---\n"
            for chunk in target_chunks[:5]:  # Max 5 chunks per target
                comparison_context += chunk.get('content', '') + "\n"
            comparison_context += "\n"

        # Create synthetic chunk for synthesis
        comparison_chunk = {
            'content': comparison_context,
            'chunk_type': 'comparison',
            'page': chunks[0].get('page', 1) if chunks else 1
        }

        # Synthesize answer with comparison prompt
        return synthesize_answer_sync(
            query=query,
            chunks=[comparison_chunk] + chunks[:10],
            filename=filename
        )

    def _deduplicate_extracted_items(self, answer: str) -> str:
        """Remove duplicate items from exhaustive extraction answer."""
        if not answer:
            return answer

        lines = answer.split('\n')
        seen = set()
        unique_lines = []

        for line in lines:
            # Normalize line for comparison
            normalized = line.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_lines.append(line)
            elif not normalized:
                unique_lines.append(line)  # Keep empty lines for formatting

        return '\n'.join(unique_lines)

    def _count_extracted_items(self, answer: str) -> int:
        """Count number of extracted items in answer."""
        if not answer:
            return 0

        # Count numbered items (1. 2. 3. etc)
        import re
        numbered = re.findall(r'^\d+\.', answer, re.MULTILINE)
        if numbered:
            return len(numbered)

        # Count bullet points
        bullets = re.findall(r'^[-•*]', answer, re.MULTILINE)
        if bullets:
            return len(bullets)

        # Count non-empty lines
        return len([l for l in answer.split('\n') if l.strip()])

    def _process_vector_only_query(
        self,
        query: str,
        process_id: str,
        filename: str,
        query_variations: List[str],
        row_col: Optional[Dict] = None,
        page_filter: int = None
    ) -> Dict[str, Any]:
        """
        Process vector-only queries using Weaviate.

        Uses parallel agents for exploratory queries (broad coverage)
        and single agent for specific queries (precise answers).

        IMPORTANT: Exploratory queries use pure BM25 (alpha=0) for keyword matching.
        Specific queries use hybrid search (alpha=0.5) for semantic + keyword.
        """
        # Detect query type for routing
        query_type_detected = detect_query_type(query)
        logger.info(f"Query type detected: {query_type_detected}")

        # Use different alpha based on query type
        # Exploratory: pure BM25 (alpha=0) to find ALL keyword matches
        # Specific: hybrid (alpha=0.5) for semantic similarity
        search_alpha = 0.0 if query_type_detected == "exploratory" else 0.5
        logger.info(f"Using alpha={search_alpha} for {query_type_detected} query")

        # Search Weaviate with optional page filter
        # Get 25 chunks for parallel processing
        chunks = self._parallel_search(
            queries=query_variations,
            process_id=process_id,
            limit_per_query=5,  # 5 * 8 overfetch = 40, then top 25 after rerank
            page_filter=page_filter,
            alpha=search_alpha  # Pass dynamic alpha: 0.0 for exploratory, 0.5 for specific
        )

        if not chunks:
            return {
                'answer': "I couldn't find any relevant information in the document.",
                'references': [],
                'confidence': 0.0,
                'query_type': 'vector_only',
                'error': False
            }

        # Use parallel agents for ALL queries when there are many chunks (>5)
        # This ensures we don't miss any relevant data regardless of query type
        # User can wait ~2 seconds extra for comprehensive results
        if len(chunks) > 5:
            logger.info(f"Using PARALLEL AGENTS with {len(chunks)} chunks (query_type={query_type_detected})")
            # Run parallel agent workflow
            result = run_parallel_agents_sync(
                query=query,
                chunks=chunks,
                filename=filename
            )

            # Format response
            response = {
                'answer': result.get('answer', ''),
                'references': format_references_for_frontend(result.get('references', [])),
                'confidence': result.get('confidence', 0.5),
                'query_type': 'vector_only',
                'cell_ids': result.get('cell_ids', []),
                'agents_used': result.get('agents_used', 1),
                'low_confidence': result.get('confidence', 0.5) < 0.7,
                'error': False
            }
            return response
        else:
            # Use single agent only when we have 5 or fewer chunks
            logger.info(f"Using SINGLE AGENT with {len(chunks)} chunks (<=5)")
            chunks_for_synthesis = chunks[:5]

            # Synthesize answer
            answer_data = synthesize_answer_sync(
                query=query,
                chunks=chunks_for_synthesis,
                filename=filename,
                row_col_position=row_col
            )

            # Add disclaimer if needed
            answer_data = add_confidence_disclaimer(answer_data)

            # Extract references (use all chunks for grounding map)
            response = build_response_with_references(
                answer_data=answer_data,
                chunks=chunks,  # Use all chunks for grounding lookup
                query_type='vector_only'
            )

            return response

    def _extract_header_patterns(
        self,
        query: str,
        chunks: List[Dict]
    ) -> List[str]:
        """
        DYNAMICALLY extract column headers from Weaviate chunks' cell_grounding.

        This parses the actual table structure from Weaviate chunks instead of
        using hardcoded terms. Headers are cells in row 0 or row 1.

        Args:
            query: User's query (used for semantic matching)
            chunks: Retrieved Weaviate chunks with cell_grounding

        Returns:
            List of actual column headers that semantically match the query
        """
        import json as json_module

        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Collect all headers from chunk cell_grounding
        all_headers = []

        for chunk in chunks[:10]:  # Check top 10 chunks
            # Skip non-table chunks
            if chunk.get('chunk_type') != 'table':
                continue

            cell_grounding_str = chunk.get('cell_grounding')
            if not cell_grounding_str:
                continue

            try:
                # Parse cell_grounding JSON
                cell_grounding = json_module.loads(cell_grounding_str)

                # Extract header cells (row 0 or row 1)
                for cell_id, cell_data in cell_grounding.items():
                    row = cell_data.get('row', -1)
                    if row in [0, 1]:  # Header rows
                        header_text = cell_data.get('text', '').strip()
                        if header_text and len(header_text) > 1:
                            all_headers.append({
                                'text': header_text,
                                'chunk_index': chunk.get('chunk_index'),
                                'col': cell_data.get('col', 0)
                            })
            except (json_module.JSONDecodeError, TypeError) as e:
                logger.debug(f"Error parsing cell_grounding: {e}")
                continue

        # Score headers by semantic relevance to query
        scored_headers = []
        for header in all_headers:
            header_text = header['text'].lower()

            # Calculate relevance score
            score = 0
            # Exact word match
            for word in query_words:
                if word in header_text:
                    score += 10
            # Partial match
            for word in query_words:
                if len(word) > 3 and word[:4] in header_text:
                    score += 5

            if score > 0:
                scored_headers.append({
                    'text': header['text'],
                    'score': score,
                    'chunk_index': header['chunk_index']
                })

        # Sort by score and deduplicate
        scored_headers.sort(key=lambda x: x['score'], reverse=True)

        seen = set()
        unique_patterns = []
        for h in scored_headers:
            text_lower = h['text'].lower()
            if text_lower not in seen:
                seen.add(text_lower)
                unique_patterns.append(h['text'])

        # If no semantic matches, fall back to ALL unique headers
        if not unique_patterns and all_headers:
            logger.info("No semantic header match, using all headers from chunks")
            seen = set()
            for h in all_headers:
                text_lower = h['text'].lower()
                if text_lower not in seen and len(h['text']) > 1:
                    seen.add(text_lower)
                    unique_patterns.append(h['text'])

        logger.info(f"Extracted {len(unique_patterns)} dynamic headers from Weaviate: {unique_patterns[:5]}")
        return unique_patterns[:5]

    def _format_neo4j_results_for_synthesis(
        self,
        results: List[Dict]
    ) -> str:
        """
        Format Neo4j query results into a string for LLM synthesis.

        IMPROVED: Handles DYNAMIC Cypher results where column names vary.
        The LLM-generated Cypher may return different keys like:
        - 'text', 'value', 'cell_text', 'content'
        - 'row', 'row_num', 'row_number'
        - 'col', 'column', 'col_num'
        - 'header', 'column_header', 'header_text'

        This function now auto-detects and formats ANY result structure.
        """
        if not results:
            return "No data found."

        # If results are simple and we got just one record, format it directly
        if len(results) == 1:
            item = results[0]
            if isinstance(item, dict):
                parts = []
                for key, value in item.items():
                    if value is not None and str(value).strip():
                        parts.append(f"**{key}**: {value}")
                if parts:
                    return "Found data:\n" + "\n".join(parts)

        # Auto-detect column structure from first result
        sample = results[0] if results else {}

        # Map common Neo4j result keys to standard names
        key_mappings = {
            'text': ['text', 'value', 'cell_text', 'content', 'data'],
            'row': ['row', 'row_num', 'row_number', 'r'],
            'col': ['col', 'column', 'col_num', 'column_num', 'c'],
            'header': ['header', 'column_header', 'header_text', 'column_name'],
            'page': ['page', 'page_num', 'page_number']
        }

        def find_key(item: Dict, possible_keys: List[str]) -> Any:
            """Find first matching key in item."""
            for key in possible_keys:
                if key in item:
                    return item[key]
            return None

        # Try to intelligently format based on result structure
        output_parts = []

        # Check if results look like row data (cells from same row)
        has_row_structure = 'row' in sample or 'row_num' in sample
        has_col_structure = 'col' in sample or 'col_num' in sample or 'column' in sample

        if has_row_structure and has_col_structure:
            # Results are cell-based - format as table row
            output_parts.append("**Row Data Found:**\n")

            # Group by row number
            by_row = {}
            for item in results:
                row_num = find_key(item, key_mappings['row']) or 0
                if row_num not in by_row:
                    by_row[row_num] = []
                by_row[row_num].append(item)

            for row_num, cells in by_row.items():
                output_parts.append(f"\n*Row {row_num}:*")
                for cell in cells:
                    col = find_key(cell, key_mappings['col']) or '?'
                    text = find_key(cell, key_mappings['text']) or ''
                    header = find_key(cell, key_mappings['header']) or f'Column {col}'
                    if text:
                        output_parts.append(f"  - {header}: {text}")

        elif 'column_header' in sample or 'header' in sample:
            # Results are grouped by column - original format
            by_header = {}
            for item in results:
                header = find_key(item, key_mappings['header']) or 'Unknown'
                if header not in by_header:
                    by_header[header] = []
                by_header[header].append({
                    'row_label': item.get('row_label', ''),
                    'value': find_key(item, key_mappings['text']) or '',
                    'page': find_key(item, key_mappings['page']) or 1
                })

            for header, rows in by_header.items():
                output_parts.append(f"\n**{header}** column data:\n")
                for row in rows[:20]:
                    label = row['row_label'] if row['row_label'] else "Row"
                    output_parts.append(f"- {label}: {row['value']} (Page {row['page']})")

        else:
            # Generic format - just output all key-value pairs
            output_parts.append("**Query Results:**\n")
            for i, item in enumerate(results[:30], 1):  # Limit to 30 items
                if isinstance(item, dict):
                    item_parts = []
                    for key, value in item.items():
                        if value is not None and str(value).strip() and not key.startswith('_'):
                            item_parts.append(f"{key}={value}")
                    if item_parts:
                        output_parts.append(f"{i}. {', '.join(item_parts)}")
                else:
                    output_parts.append(f"{i}. {item}")

        return '\n'.join(output_parts) if output_parts else "Data found but could not format: " + str(results[:5])

    def process_query_sync(
        self,
        query: str,
        process_id: str,
        filename: str = "document",
        recent_messages: List[Dict[str, str]] = None,
        use_cache: bool = True,
        use_llm_rephraser: bool = True,
        precomputed_plan: 'ExecutionPlan' = None,
        precomputed_discovery: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Synchronous version of query processing with Phase 6 intent routing.

        Intent Routing:
        - vector_only: Weaviate semantic search (90% of queries)
        - structural: Neo4j only (page finding, table structure)
        - hybrid_semantic_structural: Weaviate → Neo4j (column extraction)
        - extraction: Neo4j bulk extraction

        Args:
            query: User's question
            process_id: Document UUID for Weaviate/Neo4j filtering
            filename: Original document filename
            recent_messages: Last 3 messages for context resolution
            use_cache: Whether to use semantic cache
            use_llm_rephraser: Whether to use LLM for query variations
            precomputed_plan: Pre-computed ExecutionPlan from streaming endpoint (avoids duplicate classification)
            precomputed_discovery: Pre-computed discovery result for Visual Audit (avoids duplicate discovery)

        Returns:
            Complete response with answer, references, confidence, etc.
        """
        logger.info(f"Processing query: '{query[:50]}...' for process_id={process_id[:8]}...")

        # Step 1: Context Resolution (resolve pronouns like "it", "that")
        if recent_messages:
            query = resolve_context_references(query, recent_messages)
            logger.debug(f"After context resolution: '{query[:50]}...'")

        # Step 1.5: Check if this is a Visual Audit page selection follow-up
        # Only check context if query looks like a follow-up (saves ~2s latency for new queries)
        query_lower = query.lower()
        needs_context_check = (
            recent_messages and len(recent_messages) >= 2 and
            (
                # Only check if query contains follow-up indicators
                'same page' in query_lower or
                'that page' in query_lower or
                'check again' in query_lower or
                'deep check' in query_lower or
                'verify' in query_lower or
                'not correct' in query_lower or
                # Or if it's just a page number (e.g., "31", "page 31")
                (len(query.split()) <= 3 and any(c.isdigit() for c in query)) or
                # Or if previous message asked "which page"
                any('which page' in msg.get('content', '').lower() for msg in recent_messages[-2:] if msg.get('role') == 'assistant')
            )
        )

        if needs_context_check:
            logger.info(f"[CONTEXT_CHECK] Checking for follow-up. Query: '{query[:50]}...'")
            # Log what messages we're analyzing (debug level)
            for i, msg in enumerate(recent_messages[-4:]):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100]
                logger.debug(f"[CONTEXT_CHECK] Message {i}: {role} - {content}...")

            context_analysis = analyze_conversation_context(query, recent_messages)
            logger.info(f"[PAGE_SELECTION_DEBUG] Context analysis result: {context_analysis}")

            # Handle both page_selection AND follow_up_verification
            action_type = context_analysis.get("action_type", "new_query")
            pages_from_context = context_analysis.get("pages")
            original_query = context_analysis.get("original_query", "")

            # Check if we have pages to analyze (from either action type)
            if (action_type in ["page_selection", "follow_up_verification"] and pages_from_context) or \
               (context_analysis.get("is_page_selection") and pages_from_context):
                logger.info(f"Context analysis: action={action_type}, pages={pages_from_context}")

                # Go directly to Stage 2 deep analysis
                pages_to_analyze = pages_from_context
                resolved_query = original_query if original_query else query

                # Construct PDF path - use ABSOLUTE path with multiple patterns
                import re as re_module
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                temp_dir = os.path.join(backend_dir, 'temp')

                pdf_path = None
                search_paths = [
                    os.path.join(temp_dir, filename),
                    os.path.join(temp_dir, filename.replace(' ', '_')),
                ]

                # Also try sanitized version
                sanitized = filename.replace('.pdf', '').replace('.PDF', '')
                sanitized = sanitized.replace(' ', '_').replace('(', '').replace(')', '')
                sanitized = re_module.sub(r'[^a-zA-Z0-9_\-]', '_', sanitized)
                sanitized = re_module.sub(r'_+', '_', sanitized).rstrip('_')
                search_paths.append(os.path.join(temp_dir, f"{sanitized}.pdf"))

                for path in search_paths:
                    if os.path.exists(path):
                        pdf_path = path
                        logger.info(f"Found PDF at: {pdf_path}")
                        break

                if pdf_path:
                    logger.info(f"Context analysis ({action_type}): routing to Stage 2 deep analysis for pages {pages_to_analyze}, query='{resolved_query[:50]}...'")
                    response = self._process_visual_audit_deep_analysis(
                        query=resolved_query,  # Use the resolved query with actual page number
                        process_id=process_id,
                        pdf_path=pdf_path,
                        page_numbers=pages_to_analyze[:3],  # Max 3 pages
                        chunks=None  # Will fetch from Weaviate
                    )

                    # Add context about the action type
                    if response.get('answer'):
                        pages_str = ', '.join(map(str, pages_to_analyze[:3]))
                        prefix = f"**Deep Analysis of Page(s) {pages_str}**"
                        if action_type == "follow_up_verification":
                            prefix += " (Follow-up Verification)"
                        response['answer'] = f"{prefix}\n\n{response['answer']}"

                    return response
                else:
                    logger.warning(f"PDF not found. Searched: {search_paths}")

        # Step 2: Check Semantic Cache
        query_embedding = None
        if use_cache:
            query_embedding = self._get_query_embedding(query)
            if query_embedding:
                cached_response = self.cache.get(process_id, query_embedding, query)
                if cached_response:
                    logger.info("Cache HIT - returning cached response")
                    return cached_response

        # Step 3: Intent Classification with ExecutionPlan (Phase 8)
        # Use precomputed plan if provided (from streaming endpoint), otherwise classify
        if precomputed_plan:
            plan = precomputed_plan
            logger.info(f"Using precomputed plan: {plan.intent.value} | strategy: {plan.agent_strategy.value} | confidence: {plan.confidence:.2f}")
        else:
            plan = classify_with_plan(query, use_llm=True)
            logger.info(f"Query intent: {plan.intent.value} | strategy: {plan.agent_strategy.value} | confidence: {plan.confidence:.2f}")

        # Step 4: Route based on ExecutionPlan intent (Phase 8 Dynamic Routing)
        response = None

        if plan.intent == QueryIntent.PRECISION:
            # PHASE 8: Fast path for single value lookups
            logger.info("Routing to PRECISION handler (single agent, fast path)")
            response = self._process_precision_query(query, process_id, filename, plan)

        elif plan.intent == QueryIntent.EXPLORATORY:
            # PHASE 8: General Q&A with parallel agents + Final Synthesis
            logger.info("Routing to EXPLORATORY handler (5 parallel agents + synthesis)")
            response = self._process_exploratory_query(query, process_id, filename, plan, recent_messages)

        elif plan.intent == QueryIntent.EXHAUSTIVE:
            # PHASE 8: Extract ALL instances + Final Synthesis
            logger.info("Routing to EXHAUSTIVE handler (8 parallel agents, max recall + synthesis)")
            response = self._process_exhaustive_query(query, process_id, filename, plan, recent_messages)

        elif plan.intent == QueryIntent.CROSS_REFERENCE:
            # PHASE 9: Multi-step locate + extract for ambiguous cross-page queries
            logger.info("Routing to CROSS_REFERENCE handler (locate + extract across pages)")
            response = self._process_cross_reference_query(query, process_id, filename, plan, recent_messages)

        elif plan.intent == QueryIntent.COMPARISON:
            # PHASE 8: Compare two or more items
            logger.info(f"Routing to COMPARISON handler (targets: {plan.comparison_targets})")
            response = self._process_comparison_query(query, process_id, filename, plan)

        elif plan.intent == QueryIntent.STRUCTURAL:
            # DEPRECATED: Route to EXPLORATORY instead (structural removed in Phase 8)
            logger.info("STRUCTURAL deprecated - routing to EXPLORATORY handler")
            response = self._process_exploratory_query(query, process_id, filename, plan, recent_messages)

        elif plan.intent == QueryIntent.HYBRID_SEMANTIC_STRUCTURAL:
            # Weaviate → Neo4j - column extraction across pages
            logger.info("Routing to HYBRID_SEMANTIC_STRUCTURAL handler (Weaviate → Neo4j)")
            query_variations = rephrase_question_sync(query, use_llm=use_llm_rephraser)
            response = self._process_hybrid_query(
                query, process_id, filename, query_variations
            )

        elif plan.intent == QueryIntent.EXTRACTION:
            # Neo4j bulk extraction
            logger.info("Routing to EXTRACTION handler (Neo4j)")
            response = self._process_extraction_query(query, process_id, filename)

        elif plan.intent == QueryIntent.VISUAL_AUDIT:
            # Phase 7: Visual Audit with Gemini multimodal
            logger.info("Routing to VISUAL_AUDIT handler (Gemini multimodal)")
            response = self._process_visual_audit_query(query, process_id, filename, precomputed_discovery)

        elif plan.intent == QueryIntent.CLARIFICATION:
            # Ask for clarification
            response = {
                'answer': "Could you please provide more details about what you're looking for? For example, specify the table name, page number, or specific data you need.",
                'references': [],
                'confidence': 0.5,
                'query_type': 'clarification',
                'intent': plan.intent.value,
                'error': False
            }

        else:
            # Legacy fallback: vector_only (for backward compatibility)
            logger.info("Routing to VECTOR_ONLY handler (legacy fallback)")

            # Check for row/col position query
            row_col = detect_row_col_query(query)
            if row_col:
                logger.info(f"Row/col query detected: row={row_col['row']}, col={row_col['col']}")

            # Check for page filter in query (e.g., "from page 5")
            page_filter = detect_page_filter(query)
            if page_filter:
                logger.info(f"Page filter detected: page {page_filter}")

            # Process with vector-only handler
            query_variations = [query]
            response = self._process_vector_only_query(
                query, process_id, filename, query_variations, row_col, page_filter
            )

        # Step 5: Update Cache
        if use_cache and query_embedding and response:
            self.cache.set(process_id, query_embedding, response, query)
            logger.debug("Response cached")

        logger.info(f"Response generated with confidence={response.get('confidence', 0):.2f}")

        return response

    async def process_query(
        self,
        query: str,
        process_id: str,
        filename: str = "document",
        recent_messages: List[Dict[str, str]] = None,
        use_cache: bool = True,
        use_llm_rephraser: bool = True
    ) -> Dict[str, Any]:
        """
        Async version of query processing.

        Args:
            query: User's question
            process_id: Document UUID for Weaviate filtering
            filename: Original document filename
            recent_messages: Last 3 messages for context resolution
            use_cache: Whether to use semantic cache
            use_llm_rephraser: Whether to use LLM for query variations

        Returns:
            Complete response with answer, references, confidence, etc.
        """
        # Run sync version in thread pool for now
        # Can be made fully async later with aiohttp
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.process_query_sync(
                query=query,
                process_id=process_id,
                filename=filename,
                recent_messages=recent_messages,
                use_cache=use_cache,
                use_llm_rephraser=use_llm_rephraser
            )
        )

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get semantic cache statistics."""
        return self.cache.get_stats()

    def invalidate_cache(self, process_id: str) -> int:
        """Invalidate cache for a specific document."""
        return self.cache.invalidate(process_id)

    def clear_cache(self) -> int:
        """Clear all cache entries."""
        return self.cache.clear()


# Global orchestrator instance
_orchestrator_instance: Optional[RAGOrchestrator] = None


def get_rag_orchestrator() -> RAGOrchestrator:
    """Get or create the global RAG orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = RAGOrchestrator()
    return _orchestrator_instance


async def process_rag_query(
    query: str,
    process_id: str,
    filename: str = "document",
    recent_messages: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to process a RAG query.

    Args:
        query: User's question
        process_id: Document UUID
        filename: Document filename
        recent_messages: Recent conversation messages

    Returns:
        RAG response dict
    """
    orchestrator = get_rag_orchestrator()
    return await orchestrator.process_query(
        query=query,
        process_id=process_id,
        filename=filename,
        recent_messages=recent_messages
    )


def process_rag_query_sync(
    query: str,
    process_id: str,
    filename: str = "document",
    recent_messages: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Synchronous convenience function to process a RAG query.

    Args:
        query: User's question
        process_id: Document UUID
        filename: Document filename
        recent_messages: Recent conversation messages

    Returns:
        RAG response dict
    """
    orchestrator = get_rag_orchestrator()
    return orchestrator.process_query_sync(
        query=query,
        process_id=process_id,
        filename=filename,
        recent_messages=recent_messages
    )

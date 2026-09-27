# Services package for OCR Chatbot
#
# Phase 3: Layout-Aware Chunking
# - textract_parser.py - Parse AWS Textract blocks
# - chunk_transformer.py - Transform blocks into searchable chunks
# - weaviate_indexer.py - Index chunks to Weaviate
#
# Phase 4: Multi-Agent RAG Orchestration
# - semantic_cache.py - Query caching with similarity threshold
# - intent_classifier.py - Query intent classification
# - question_rephraser.py - Query variation generation
# - answer_synthesizer.py - Answer generation with cell references
# - reference_extractor.py - Bbox extraction from cell_grounding
# - rag_orchestrator.py - Main orchestration logic
#
# Database
# - database.py - PostgreSQL chat history persistence

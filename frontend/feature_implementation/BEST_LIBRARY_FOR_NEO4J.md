# Best Library for Neo4j + Claude Backend Integration

> **Purpose:** Recommend the best library for Python backend to query Neo4j using Claude
> **Date:** January 28, 2026
> **Decision:** `neo4j-graphrag` (Official Neo4j Package)
> **Status:** ✅ FINAL RECOMMENDATION

---

## Quick Answer

**Use `neo4j-graphrag`** - Official Neo4j Python package for GraphRAG applications.

```bash
pip install "neo4j-graphrag[anthropic]"
```

---

## Why neo4j-graphrag?

| Reason | Details |
|--------|---------|
| **Official Neo4j Package** | Long-term support guaranteed, regular updates |
| **Claude/Anthropic Native** | Built-in `AnthropicLLM` class |
| **Auto Schema Discovery** | Fetches schema automatically from Neo4j |
| **Built-in Cypher Validation** | Validates queries before execution |
| **Auto-Retry on Errors** | Sends error back to LLM for fix |
| **Text2CypherRetriever** | Natural language → Cypher → Results |
| **Production Ready** | Enterprise-grade, battle-tested |

---

## All Options Compared

| Feature | neo4j-graphrag | LangChain | Direct API |
|---------|----------------|-----------|------------|
| **Schema Auto-Discovery** | ✅ Built-in | ✅ Built-in | ⚠️ Manual (APOC) |
| **Cypher Validation** | ✅ Built-in | ✅ Built-in | ⚠️ Manual (EXPLAIN) |
| **Auto-Retry on Error** | ✅ Built-in | ⚠️ Limited | ⚠️ Manual |
| **Claude Support** | ✅ Native | ✅ Native | ✅ Native |
| **Official Neo4j Support** | ✅ Yes | ❌ Community | ❌ None |
| **Code Complexity** | Low | Low | High |
| **Flexibility** | Medium | Medium | High |
| **Long-term Maintenance** | ✅ Guaranteed | ⚠️ Community | ❌ You |

---

## Installation

```bash
# Basic installation
pip install neo4j-graphrag

# With Claude/Anthropic support (RECOMMENDED)
pip install "neo4j-graphrag[anthropic]"

# With OpenAI support
pip install "neo4j-graphrag[openai]"

# Full installation with all features
pip install "neo4j-graphrag[anthropic,openai,experimental]"
```

---

## Quick Start Example

```python
from neo4j import GraphDatabase
from neo4j_graphrag.llm import AnthropicLLM
from neo4j_graphrag.retrievers import Text2CypherRetriever

# Connect to Neo4j
driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password")
)

# Initialize Claude LLM
llm = AnthropicLLM(
    model_name="claude-3-5-sonnet-20241022",
    model_params={"temperature": 0, "max_tokens": 4000}
)

# Create Text2Cypher retriever - AUTO schema discovery!
retriever = Text2CypherRetriever(
    driver=driver,
    llm=llm,
    neo4j_schema=None  # Auto-fetches schema from Neo4j
)

# Query in natural language
results = retriever.search("Find all pages containing Sample Summary sections")

# Results contain the data from Neo4j
for item in results.items:
    print(item)

driver.close()
```

---

## Available Retrievers

| Retriever | Use Case | Description |
|-----------|----------|-------------|
| **Text2CypherRetriever** | Natural language queries | LLM generates Cypher from question |
| **VectorRetriever** | Similarity search | Vector-based retrieval |
| **HybridRetriever** | BM25 + Vector | Combined keyword and semantic search |
| **VectorCypherRetriever** | Vector + Graph traversal | Vector search with Cypher post-processing |
| **HybridCypherRetriever** | Hybrid + Graph traversal | Hybrid search with Cypher post-processing |

---

## Text2CypherRetriever Deep Dive

### How It Works

```
User Question: "Find pages with Sample Summary"
         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Fetch Schema (automatic)                            │
│ ─────────────────────────────────                           │
│ Retriever calls Neo4j APOC to get:                          │
│ - Node labels: Document, Page, Section, Table, Cell         │
│ - Relationships: HAS_PAGE, CONTAINS_SECTION, HAS_CELL       │
│ - Properties: pageNumber, section_title, text, row, col     │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Generate Cypher (Claude)                            │
│ ─────────────────────────────────                           │
│ Sends schema + question to Claude                           │
│ Claude generates:                                           │
│   MATCH (p:Page)-[:CONTAINS_SECTION]->(s:Section)          │
│   WHERE toLower(s.section_title) CONTAINS 'sample summary' │
│   RETURN p.pageNumber AS page                               │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Validate Cypher (automatic)                         │
│ ─────────────────────────────────                           │
│ Uses EXPLAIN to validate syntax before execution            │
│ If error → sends error to Claude → Claude fixes → retry     │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Execute & Return Results                            │
│ ─────────────────────────────────                           │
│ Executes validated Cypher against Neo4j                     │
│ Returns structured results                                  │
└─────────────────────────────────────────────────────────────┘
```

### Configuration Options

```python
retriever = Text2CypherRetriever(
    driver=driver,
    llm=llm,

    # Schema options
    neo4j_schema=None,           # None = auto-fetch, or provide custom string

    # Validation options
    validate_cypher=True,        # Validate before execution

    # Safety options
    allow_dangerous=False,       # Block DELETE, DROP, etc.

    # Retry options
    retry_on_error=True,         # Auto-retry with error message
    max_retries=3,               # Maximum retry attempts

    # Custom prompt (optional)
    custom_prompt=None           # Override default prompt template
)
```

---

## Complete Implementation for Your Project

```python
# backend/services/neo4j_graphrag_service.py

from neo4j import GraphDatabase
from neo4j_graphrag.llm import AnthropicLLM
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.generation import GraphRAG
import os
import logging

logger = logging.getLogger(__name__)

class Neo4jGraphRAGService:
    """
    Neo4j + Claude integration using neo4j-graphrag package.
    Handles schema discovery, Cypher generation, validation, and execution.
    """

    def __init__(
        self,
        neo4j_uri: str = None,
        neo4j_user: str = None,
        neo4j_password: str = None,
        anthropic_api_key: str = None
    ):
        # Use environment variables as defaults
        self.neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = neo4j_user or os.getenv("NEO4J_USERNAME", "neo4j")
        self.neo4j_password = neo4j_password or os.getenv("NEO4J_PASSWORD", "password")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

        # Initialize Neo4j driver
        self.driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password)
        )

        # Initialize Claude LLM
        self.llm = AnthropicLLM(
            model_name="claude-3-5-sonnet-20241022",
            model_params={
                "temperature": 0,
                "max_tokens": 4000
            },
            api_key=REDACTED
        )

        # Initialize Text2Cypher retriever
        self.retriever = Text2CypherRetriever(
            driver=self.driver,
            llm=self.llm,
            neo4j_schema=None,  # Auto-fetch
            validate_cypher=True,
            retry_on_error=True,
            max_retries=3
        )

        # Initialize GraphRAG for full Q&A
        self.rag = GraphRAG(
            retriever=self.retriever,
            llm=self.llm
        )

        logger.info(f"Neo4jGraphRAGService initialized with {self.neo4j_uri}")

    def get_schema(self) -> str:
        """Get the current Neo4j schema"""
        with self.driver.session() as session:
            result = session.run("CALL apoc.meta.schema() YIELD value RETURN value")
            return str(result.single()["value"])

    def find_pages(self, doc_id: str, search_term: str) -> list[int]:
        """
        Find pages containing a specific term using Text2Cypher.

        Args:
            doc_id: Document ID to search within
            search_term: Term to search for (e.g., "Sample Summary")

        Returns:
            List of page numbers
        """
        question = f"For document {doc_id}, find all pages that contain '{search_term}'"

        try:
            results = self.retriever.search(query_text=question)
            pages = []
            for item in results.items:
                if hasattr(item, 'content') and 'page' in str(item.content).lower():
                    # Extract page numbers from results
                    pages.append(item.content)
            return pages
        except Exception as e:
            logger.error(f"Error finding pages: {e}")
            return []

    def execute_query(self, question: str) -> dict:
        """
        Execute a natural language query against Neo4j.

        Args:
            question: Natural language question

        Returns:
            Dict with results and metadata
        """
        try:
            results = self.retriever.search(query_text=question)
            return {
                "success": True,
                "results": [item.content for item in results.items],
                "count": len(results.items)
            }
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }

    def ask_with_context(self, question: str) -> str:
        """
        Full GraphRAG: Retrieve from Neo4j + Generate answer with Claude.

        Args:
            question: Natural language question

        Returns:
            Generated answer string
        """
        try:
            response = self.rag.search(query_text=question)
            return response.answer
        except Exception as e:
            logger.error(f"GraphRAG error: {e}")
            return f"Error: {str(e)}"

    def execute_cypher_template(self, template: str, params: dict) -> list:
        """
        Execute a pre-defined Cypher template (for your working queries).

        Args:
            template: Cypher query string with $param placeholders
            params: Dict of parameter values

        Returns:
            List of result records
        """
        try:
            with self.driver.session() as session:
                result = session.run(template, params)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Template execution error: {e}")
            return []

    def close(self):
        """Close Neo4j connection"""
        self.driver.close()


# Usage Example
if __name__ == "__main__":
    service = Neo4jGraphRAGService()

    # Example 1: Natural language query
    results = service.execute_query("Find all pages with Sample Summary sections")
    print("Results:", results)

    # Example 2: Full Q&A with GraphRAG
    answer = service.ask_with_context("What test parameters are on page 5?")
    print("Answer:", answer)

    # Example 3: Execute your working Cypher template
    concentration_query = """
        WITH $doc_id AS DOC_ID
        MATCH (d:Document {docId:DOC_ID})-[:HAS_PAGE]->(p:Page)-[:HAS_TABLE]->(t:Table)
        MATCH (t)-[:HAS_CELL]->(r:Cell)
        WHERE toLower(coalesce(r.text,"")) CONTAINS "range"
        // ... rest of your query
        RETURN p.pageNumber AS page
    """
    results = service.execute_cypher_template(concentration_query, {"doc_id": "7613"})
    print("Template Results:", results)

    service.close()
```

---

## Integration with Your Backend (app.py)

```python
# backend/app.py

from services.neo4j_graphrag_service import Neo4jGraphRAGService

# Initialize service
neo4j_service = Neo4jGraphRAGService()

@app.post("/api/neo4j/query")
async def query_neo4j(request: Request):
    """
    Natural language query endpoint for Neo4j.
    """
    data = await request.json()
    question = data["question"]

    result = neo4j_service.execute_query(question)
    return result

@app.post("/api/neo4j/find-pages")
async def find_pages(request: Request):
    """
    Find pages containing specific content.
    """
    data = await request.json()
    doc_id = data["doc_id"]
    search_term = data["search_term"]

    pages = neo4j_service.find_pages(doc_id, search_term)
    return {"pages": pages}

@app.post("/api/neo4j/ask")
async def ask_graphrag(request: Request):
    """
    Full GraphRAG Q&A endpoint.
    """
    data = await request.json()
    question = data["question"]

    answer = neo4j_service.ask_with_context(question)
    return {"answer": answer}
```

---

## Alternative: LangChain (If Already Using LangChain)

If you're already using LangChain in your project:

```bash
pip install langchain langchain-anthropic langchain-community neo4j
```

```python
from langchain_anthropic import ChatAnthropic
from langchain_community.graphs import Neo4jGraph
from langchain.chains import GraphCypherQAChain

# Connect to Neo4j
graph = Neo4jGraph(
    url="bolt://localhost:7687",
    username="neo4j",
    password=REDACTED
)

# Auto-refresh schema
graph.refresh_schema()

# Initialize Claude
llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0
)

# Create chain with validation
chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    verbose=True,
    validate_cypher=True,
    return_intermediate_steps=True
)

# Query
result = chain.invoke({"query": "Find pages with Sample Summary"})
print(result["result"])
print(result["intermediate_steps"])  # See generated Cypher
```

---

## Alternative: Direct API (Maximum Control)

If you need maximum control and don't want dependencies:

```python
from neo4j import GraphDatabase
import anthropic

class DirectNeo4jClaude:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password")
        )
        self.claude = anthropic.Anthropic()
        self.schema = self._fetch_schema()

    def _fetch_schema(self) -> str:
        """Fetch schema using APOC"""
        with self.driver.session() as session:
            result = session.run("CALL apoc.meta.schema() YIELD value RETURN value")
            return str(result.single()["value"])

    def query(self, question: str) -> dict:
        # Generate Cypher
        cypher = self._generate_cypher(question)

        # Validate
        valid, error = self._validate(cypher)
        if not valid:
            cypher = self._fix_cypher(cypher, error)

        # Execute
        return self._execute(cypher)

    def _generate_cypher(self, question: str) -> str:
        response = self.claude.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=REDACTED
            messages=[{
                "role": "user",
                "content": f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate Cypher:"
            }]
        )
        return response.content[0].text

    def _validate(self, cypher: str) -> tuple[bool, str]:
        try:
            with self.driver.session() as session:
                session.run(f"EXPLAIN {cypher}")
            return True, None
        except Exception as e:
            return False, str(e)

    def _fix_cypher(self, cypher: str, error: str) -> str:
        response = self.claude.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=REDACTED
            messages=[{
                "role": "user",
                "content": f"Query:\n{cypher}\n\nError:\n{error}\n\nFix the Cypher:"
            }]
        )
        return response.content[0].text

    def _execute(self, cypher: str) -> list:
        with self.driver.session() as session:
            result = session.run(cypher)
            return [dict(r) for r in result]
```

---

## Summary

| Library | When to Use |
|---------|-------------|
| **neo4j-graphrag** ⭐ | Default choice - official, full-featured, Claude native |
| **LangChain** | Already using LangChain in your project |
| **Direct API** | Need maximum control, minimal dependencies |

**For your OCR-Chatbot project: Use `neo4j-graphrag`**

```bash
pip install "neo4j-graphrag[anthropic]"
```

---

*Document Version: 1.0*
*Created: January 28, 2026*
*Recommendation: neo4j-graphrag with AnthropicLLM*

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
import requests
import json
from typing import List, Dict, Any

class InformationRetriever:
    """
    Agent that retrieves information from document sources based on multiple queries.
    """
    
    def __init__(
        self, 
        api_key: str, 
        api_url: str, 
        iliad_url: str,
        iliad_api_key: str,
        user_token: str,
        model_name: str = "REDACTED"
    ):
        """
        Initialize the information retriever agent.
        
        Args:
            api_key: Anthropic API key
            api_url: Anthropic API URL
            iliad_url: Iliad API URL
            iliad_api_key: Iliad API key
            user_token: User token for Iliad
            model_name: Name of the model to use
        """
        api_url=api_url + '/anthropic'
        self.llm =ChatAnthropic(
                            anthropic_api_url=api_url,
                            api_key=REDACTED
                            model_name="claude-3-7-sonnet-20250219")
        
        self.iliad_url = iliad_url
        self.iliad_api_key = iliad_api_key
        self.user_token = user_token
        
        # Define a tool for hybrid search within Iliad
        self.search_tool = Tool(
            name="search_source",
            func=self.search_source,
            description="Search for information in the document repository using both keywords and semantic similarity."
        )
        
        # Define tools list
        self.tools = [self.search_tool]
        
        # Create prompt template with all required variables for the React agent
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert information retriever. Your job is to search a document repository 
            for relevant information based on multiple search queries. For each query:
            
            1. Use the search_source tool to find relevant information
            2. Analyze the relevance of each result
            3. Compile the most relevant information
            4. Avoid duplicating information across queries
            5. Include citations to the source documents when appropriate
            
            Provide a consolidated response with all the relevant information you found, organized clearly.
            Include metadata about which documents or tables the information came from.

            {tools}
            
            {tool_names}
            """),
            ("human", "Queries to search:\n{queries}\n\nOriginal question: {original_question}"),
            ("human", "{agent_scratchpad}")
        ])
        
        # Create the agent
        self.agent = create_react_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
    
    def search_source(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform a hybrid search (keyword + vector) in the Iliad source.
        
        Args:
            query: The search query
            
        Returns:
            A list of search results with text and metadata
        """
        try:
            # Check if source is set
            if not self.current_source:
                return [{"error": "No source specified. Please set the source first."}]
                
            # Generate embeddings for the query
            embed_resp = requests.post(
                url=f"{self.iliad_url}/api/v1/embed/text-embedding-ada-002",
                headers={
                    "x-api-key": self.iliad_api_key,
                    "x-user-token": self.user_token
                },
                json={"input": [query]}
            )
            embed_resp.raise_for_status()
            query_vector = embed_resp.json()["embeddings"][0]
            
            # Build a hybrid search query (combining keyword and vector search)
            search_query = {
                "query": {
                    "bool": {
                        "should": [
                            # Keyword match component
                            {
                                "match": {
                                    "chunk_text": {
                                        "query": query,
                                        "boost": 1.0
                                    }
                                }
                            },
                            # Vector similarity component
                            {
                                "script_score": {
                                    "query": {"match_all": {}},
                                    "script": {
                                        "source": "cosineSimilarity(params.queryVector, 'chunk_vector') + 1.0",
                                        "params": {"queryVector": query_vector}
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": 5  # Return top 5 results
            }
            
            # Execute the search
            search_resp = requests.post(
                url=f"{self.iliad_url}/api/v1/sources/{self.current_source}/search",
                headers={
                    "x-api-key": self.iliad_api_key,
                    "x-user-token": self.user_token
                },
                json={"search": search_query}
            )
            search_resp.raise_for_status()
            
            # Process and return the results
            results = search_resp.json()
            hits = results.get("hits", {}).get("hits", [])
            
            formatted_results = []
            for hit in hits:
                source = hit.get("_source", {})
                formatted_results.append({
                    "text": source.get("chunk_text", ""),
                    "metadata": {
                        "filename": source.get("filename", ""),
                        "document_summary": source.get("document_summary", ""),
                        "is_table_data": source.get("is_table_data", False),
                        "table_name": source.get("table_name", ""),
                        "table_columns": source.get("table_columns", "")
                    },
                    "score": hit.get("_score", 0)
                })
            
            return formatted_results
        
        except Exception as e:
            print(f"Error searching source: {e}")
            return [{"error": f"Search error: {str(e)}"}]
    
    async def retrieve(self, queries: List[str], original_question: str, source_name: str) -> str:
        """
        Retrieve information based on multiple queries.
        
        Args:
            queries: List of search queries
            original_question: The original question asked by the user
            source_name: The name of the source to search
            
        Returns:
            A consolidated response with relevant information
        """
        # Set the source name for the search tool to use
        self.current_source = source_name
        
        # Format queries as a string
        queries_str = "\n".join([f"- {q}" for q in queries])
        
        # Invoke the agent
        result = await self.agent_executor.ainvoke({
            "queries": queries_str,
            "original_question": original_question
        })
        
        return result["output"]
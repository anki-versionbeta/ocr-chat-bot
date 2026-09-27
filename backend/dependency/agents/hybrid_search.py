import requests
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
import requests
import json
from typing import List, Dict, Any


class HybridSearch:
    """
    Implementation of hybrid search combining lexical (BM25) and semantic (vector) search
    to answer questions from source documents in Elasticsearch.
    """
    
    def __init__(
        self, 
        base_url: str,
        api_key: str,
        user_token: str,
        embedding_model: str = "REDACTED",#"text-embedding-ada-002",
        vector_field: str = "chunk_vector",
        content_field: str = "content",
        title_field: str = "title",
        lexical_weight: float = 0.3,
        semantic_weight: float = 0.7
    ):
        """
        Initialize the hybrid search.
        
        Args:
            base_url: Base URL for the API
            api_key: API key for authentication
            user_token: User token for authentication
            embedding_model: Model to use for embeddings
            vector_field: Field containing vector embeddings
            content_field: Field containing document content
            title_field: Field containing document title
            lexical_weight: Weight for lexical search (BM25) component
            semantic_weight: Weight for semantic search (vector) component
        """
        self.base_url = base_url
        self.headers = {
            "x-api-key": api_key,
            "x-user-token": user_token,
            "Content-Type": "application/json"
        }
        self.embedding_model = embedding_model
        self.vector_field = vector_field
        self.content_field="chunk_text",        # Main text content
        self.vector_field="chunk_vector",       # Vector embeddings
        self.title_field="filename",
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
        """
        embed_resp = requests.post(
            f"{self.base_url}/api/v1/embed/{self.embedding_model}",
            json={"input": [text]},
            headers=self.headers
        )
        embed_resp.raise_for_status()
        return embed_resp.json()["embeddings"][0]
    
    def build_hybrid_query(self, question: str) -> Dict[str, Any]:
        """
        Build a hybrid query combining lexical and semantic search.
        
        Args:
            question: Question to search for
            
        Returns:
            Elasticsearch DSL query
        """
        # Get embedding for semantic search
        question_embedding = self.get_embedding(question)
        #print(question_embedding)
        
        # Build hybrid query
        query = {
            "query": {
                "bool": {
                    "should": [
                        # Lexical match component (BM25)
                        {
                            "bool": {
                                "should": [
                                    {
                                        "match": {
                                            self.content_field: {
                                                "query": question,
                                                "boost": self.lexical_weight * 1.0,
                                                "operator": "OR"
                                            }
                                        }
                                    },
                                    {
                                        "match_phrase": {
                                            self.content_field: {
                                                "query": question,
                                                "boost": self.lexical_weight * 1.5,
                                                "slop": 2
                                            }
                                        }
                                    },
                                      
                                    {
                                    "match": {
                                        "keywords": {
                                            "query": question,
                                            "boost": self.lexical_weight * 2.5,  # Higher boost for keywords
                                            "operator": "OR"
                                        }
                                    }
                                },
                                # Add custom field: summary
                                {
                                    "match": {
                                        "summary": {
                                            "query": question,
                                            "boost": self.lexical_weight * 2.0,  # Higher boost for summary
                                            "operator": "OR"
                                        }
                                    }
                                },
                                    
                                    {
                                        "match": {
                                            self.title_field: {
                                                "query": question,
                                                "boost": self.lexical_weight * 2.0
                                            }
                                        }
                                    }
                                ]
                            }
                        },
                        # Semantic search component (vector similarity)
                        {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": f"cosineSimilarity(params.queryVector, '{self.vector_field}') * params.weight + 1.0",
                                    "params": {
                                        "queryVector": question_embedding,
                                        "weight": self.semantic_weight
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            # Request highlights to see matching sections
            "highlight": {
                "fields": {
                    self.content_field: {
                        "fragment_size": 300,
                        "number_of_fragments": 3,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"]
                    }
                }
            },
            # Return top 10 results
            "size": 10,
            # Include original content in response
            "_source": [self.content_field, self.title_field, "metadata"]
        }
        
#         query = {
#                 "query":
            
            
            
#             {
#                     "script_score": {
#                         "query": {"match_all": {}},
#                         "script": {
#                             "source": "cosineSimilarity(params.queryVector, 'chunk_vector') + 1.0",
#                             "params": {"queryVector":question_embedding,},
#                         },
#                     }
#                 }
#                 }

#         query={
#               "query": {
#                 "bool": {
#                   "should": [
#                     {
#                       "match": {
#                         "chunk_text": {
#                           "query": question,
#                           "boost": 0.3,
#                           "operator": "OR"
#                         }
#                       }
#                     },
#                     {
#                       "script_score": {
#                         "query": {"match_all": {}},
#                         "script": {
#                           "source": "cosineSimilarity(params.queryVector, 'chunk_vector') + 1.0",
#                            "params": {"queryVector":question_embedding,},
#                         }
#                       }
#                     }
#                   ]
#                 }
#               }
#             }
        
        query={
              "query": {
                "bool": {
                  "should": [
                    {
                      "match": {
                        "chunk_text": {
                          "query": question,
                          "boost": 0.3,
                          "operator": "OR"
                        }
                      }
                    },
                    {
                      "match": {
                        "filename": {
                          "query": question,
                          "boost": 0.2,
                          "operator": "OR"
                        }
                      }
                    },
                    {
                      "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                          "source": "cosineSimilarity(params.queryVector, 'chunk_vector') * params.weight + 1.0",
                          "params": {
                            "queryVector": question_embedding,
                            "weight": 0.7
                          }
                        }
                      }
                    }
                  ]
                }
              },
            "size": 10
            }
        return query
    
    def search(self, source_name: str, question: str) -> Dict[str, Any]:
        """
        Perform hybrid search on a source.
        
        Args:
            source_name: Name of the source to search
            question: Question to search for
            included_files: Files to be included for context
            
        Returns:
            Search results
        """
        # Build query
        search_query = self.build_hybrid_query(question)
#         print("########### Query #############")
#         print(search_query)
        # Execute search
        search_resp = requests.post(
            url=f"{self.base_url}/api/v1/sources/{source_name}/search",
            headers=self.headers,
            json={"search": search_query
                 #,"filters": {"term":{'filename':included_files}}
                 }
        )
#         print("############ Search ################")
#         print(search_resp.json())
        #print(search_resp.raise_for_status())
        
        return search_resp.json()
    
    def answer_question(self, source_name: str, question: str, filter_list: list) -> Dict[str, Any]:
        """
        Answer a question using hybrid search.
        
        Args:
            source_name: Name of the source to search
            question: Question to answer
            
        Returns:
            Dictionary with question, answer, and supporting passages
        """
        # Get search results
        search_results = self.search(source_name, question)
        
        # Extract relevant passages and build context
        passages = []
        print("############# Hybrid search ################")
        print(search_results)
        #print(search_results['hits']['hits'][0])
        for hit in search_results.get("hits", {}).get("hits", []):
            #content = hit.get("_source", {}).get(self.content_field, "")
            sources = hit.get("_source", {})
            
            filename = hit.get("_source", {}).get('filename', "")
            score = hit.get("_score", 0)
            chunk_text = hit.get("_source", {}).get("chunk_text", "")
            
            if sources.get("filename") in filter_list :
                filename = sources.get("filename")
                chunk_text = sources.get("chunk_text", "")
                print(f"Filename inside library: {filename}")
                
                
                # Get highlights if available
                highlights = []
                if "highlight" in hit:
                    for field, fragments in hit["highlight"].items():
                        highlights.extend(fragments)
            
                # If no highlights, use content directly
                passage_text = " ".join(highlights) if highlights else ""
                
                passages.append({
                    "text": chunk_text,
                    "filename": filename,
                    "score": score,
                    "highlight":passage_text
                })
#                 print("passages", passages)
        
        return {
            "question": question,
            "passages": passages,
        }
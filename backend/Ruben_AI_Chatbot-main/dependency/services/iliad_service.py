import os
import json
import requests
from typing import Dict, Any, List, Optional, Union
import tempfile

class IliadService:
    """
    Service for interacting with the Iliad API for document storage and retrieval.
    """
    
    def __init__(self, iliad_url: str, iliad_api_key: str, user_token: str):
        """
        Initialize the Iliad service.
        
        Args:
            iliad_url: Base URL for the Iliad API
            iliad_api_key: API key for Iliad
            user_token: User token for authentication
        """
        self.iliad_url = iliad_url
        self.iliad_api_key = iliad_api_key
        self.user_token = user_token
        self.headers = {
            "x-api-key": iliad_api_key,
            "x-user-token": user_token
        }
    
    def list_sources(self) -> List[Dict[str, Any]]:
        """
        List all available sources.
        
        Returns:
            List of source objects
        """
        try:
            response = requests.get(
                url=f"{self.iliad_url}/api/v1/sources/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json().get("private_sources", [])
        except Exception as e:
            print(f"Error listing sources: {e}")
            return []
    
    def create_source(self, source_name: str, description: str = "", custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new source.
        
        Args:
            source_name: Name of the source to create
            description: Description of the source
            custom_fields: Dictionary of custom fields to add to the source
            
        Returns:
            Created source object
        """
        try:
            # Check if source already exists
            try:
                response = requests.get(
                    url=f"{self.iliad_url}/api/v1/sources/{source_name}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.json()
            except:
                pass
            
            # Create default custom fields if none provided
            if custom_fields is None:
                custom_fields = {
                    "filename": {"type": "text"},
                    "document_summary": {"type": "text"},
                    "keywords": {"type": "text"},
                    "has_tables": {"type": "boolean"},
                    "table_count": {"type": "integer"},
                    "table_name": {"type": "text"},
                    "table_columns": {"type": "text"},
                    "is_table_data": {"type": "boolean"},
                    "subject": {"type": "text"}
                }
            
            # Create the source
            response = requests.post(
                url=f"{self.iliad_url}/api/v1/sources",
                headers=self.headers,
                json={
                    "source": source_name,
                    "description": description,
                    "custom_fields": json.dumps(custom_fields)
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error creating source: {e}")
            raise
    
    def upload_document(
        self, 
        source_name: str, 
        file_path: str, 
        custom_fields: Optional[Dict[str, Any]] = None,
        chunk_size: int = 300,
        chunk_overlap: int = 50
    ) -> Dict[str, Any]:
        """
        Upload a document to a source.
        
        Args:
            source_name: Name of the source to upload to
            file_path: Path to the file to upload
            custom_fields: Dictionary of custom fields to add to the document
            chunk_size: Size of chunks to split the document into
            chunk_overlap: Overlap between chunks
            
        Returns:
            Response from the upload request
        """
        try:
           
            params = {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap}

            if custom_fields:
                params["custom_fields"] = json.dumps(custom_fields)

            response = requests.post(
                url=f"{self.iliad_url}/api/v1/sources/{source_name}/documents",
                headers=self.headers,
                files={'file':open(file_path,"rb")},
                params=params
            )
            response.raise_for_status()
            print(response)
            print( response.json().get("task_id"))
            return {"status": "success", "task_id": response.json().get("task_id")}
        except Exception as e:
            print(f"Error uploading document: {e}")
            raise
    
    def upload_content(
        self, 
        source_name: str, 
        content: str,
        filename: str,
        custom_fields: Optional[Dict[str, Any]] = None,
        chunk_size: int = 300, 
        chunk_overlap: int = 50
    ) -> Dict[str, Any]:
        """
        Upload text content as a document.
        
        Args:
            source_name: Name of the source to upload to
            content: Text content to upload
            filename: Name to give the uploaded file
            custom_fields: Dictionary of custom fields to add to the document
            chunk_size: Size of chunks to split the document into
            chunk_overlap: Overlap between chunks
            
        Returns:
            Response from the upload request
        """
        try:
            # Write content to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp:
                temp.write(content)
                temp_path = temp.name
            
            # Upload the temporary file
            result = self.upload_document(
                source_name=source_name,
                file_path=temp_path,
                custom_fields=custom_fields,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            
            # Clean up the temporary file
            os.unlink(temp_path)
            
            return result
        except Exception as e:
            print(f"Error uploading content: {e}")
            raise
    
    def list_documents(self, source_name: str) -> List[Dict[str, Any]]:
        """
        List documents in a source.
        
        Args:
            source_name: Name of the source to list documents from
            
        Returns:
            List of document objects
        """
        try:
            response = requests.get(
                url=f"{self.iliad_url}/api/v1/sources/{source_name}/documents",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json().get("documents", [])
        except Exception as e:
            print(f"Error listing documents: {e}")
            return []
    
    def search_source(
        self, 
        source_name: str, 
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Perform a hybrid search on a source.
        
        Args:
            source_name: Name of the source to search
            query: Search query
            filters: Dictionary of filters to apply to the search
            k: Number of results to return
            
        Returns:
            List of search results
        """
        try:
            # Generate embeddings for the query
            embed_resp = requests.post(
                url=f"{self.iliad_url}/api/v1/embed/text-embedding-ada-002",
                headers=self.headers,
                json={"input": [query]}
            )
            embed_resp.raise_for_status()
            query_vector = embed_resp.json()["embeddings"][0]
            
            # Build search query
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
                "size": k
            }
            
            # Add filters if provided
            if filters:
                filter_conditions = []
                for key, value in filters.items():
                    if isinstance(value, list):
                        filter_conditions.append({"terms": {key: value}})
                    else:
                        filter_conditions.append({"term": {key: value}})
                
                if filter_conditions:
                    search_query["query"]["bool"]["filter"] = filter_conditions
            
            # Execute search
            search_resp = requests.post(
                url=f"{self.iliad_url}/api/v1/sources/{source_name}/search",
                headers=self.headers,
                json={"search": search_query}
            )
            search_resp.raise_for_status()
            
            # Process results
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
                        "table_columns": source.get("table_columns", ""),
                        "keywords": source.get("keywords", ""),
                        "subject": source.get("subject", "")
                    },
                    "score": hit.get("_score", 0)
                })
            
            return formatted_results
        except Exception as e:
            print(f"Error searching source: {e}")
            raise
    
    def query_rag(
        self, 
        source_name: str, 
        messages: List[Dict[str, str]],
        filters: Optional[Dict[str, Any]] = None,
        k: int = 5,
        chat_model: str = "claude-3-sonnet-20240229"
    ) -> Dict[str, Any]:
        """
        Perform a RAG query on a source.
        
        Args:
            source_name: Name of the source to query
            messages: List of message objects with role and content
            filters: Dictionary of filters to apply to the search
            k: Number of results to return in the vector search
            chat_model: Name of the chat model to use
            
        Returns:
            RAG response and references
        """
        try:
            request_data = {
                "messages": messages,
                "k": k,
                "chat_model": chat_model
            }
            
            if filters:
                request_data["filters"] = json.dumps(filters)
            
            response = requests.post(
                url=f"{self.iliad_url}/api/v1/sources/{source_name}/rag",
                headers=self.headers,
                json=request_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error querying RAG: {e}")
            raise
            
    def delete_source_document(self,source_name,document_id):
        '''
        Deletes a document from the source.
        
        Args:
            source_name: The name of source to be deleted from
            document_id: The unique identifier for a document in a source
        
        Returns:
            The status code of the response.         
        '''        
        try:
            response = requests.delete(
                url = f"{self.iliad_url}/api/v1/sources/{source_name}/documents/{document_id}",
                headers = self.headers
            )
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"Error Deleting the Document : {e}")
            return []
        
import requests
from typing import List, Dict, Any, Union

class EmbeddingService:
    """
    Service for generating embeddings for text.
    """
    
    def __init__(self, iliad_url: str, iliad_api_key: str, user_token: str, model: str = "text-embedding-ada-002"):
        """
        Initialize the embedding service.
        
        Args:
            iliad_url: Base URL for the Iliad API
            iliad_api_key: API key for Iliad
            user_token: User token for authentication
            model: Name of the embedding model to use
        """
        self.iliad_url = iliad_url
        self.iliad_api_key = iliad_api_key
        self.user_token = user_token
        self.model = model
        # Only include user token if it's not empty
        self.headers = {"x-api-key": iliad_api_key}
        if user_token:
            self.headers["x-user-token"] = user_token
    
    def embed_text(self, text: Union[str, List[str]]) -> List[List[float]]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text or list of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            # Ensure text is a list
            if isinstance(text, str):
                text = [text]
            
            response = requests.post(
                url=f"{self.iliad_url}/api/v1/embed/{self.model}",
                headers=self.headers,
                json={"input": text}
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            raise
    
    def batch_embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for a large batch of texts by processing in smaller batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Size of batches to process
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.embed_text(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
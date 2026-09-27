from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from typing import List, Dict, Any

class QuestionRephraser:
    """
    Agent that rephrases a question into multiple search queries to maximize
    information retrieval effectiveness.
    """

    def __init__(self, api_key: str, api_url: str, model_name: str = "REDACTED"):
        """
        Initialize the question rephraser agent.

        Args:
            api_key: Anthropic API key
            api_url: Anthropic API URL
            model_name: Name of the model to use
        """
        api_url = api_url + '/anthropic'
        self.llm = ChatAnthropic(
            anthropic_api_url=api_url,
            api_key=REDACTED
            model_name="claude-3-7-sonnet-20250219"
        )

        self.system_prompt = """You are an expert question analyzer for Certificate of Analysis (COA) documents.
Your job is to rephrase a given question into 3-5 different variations to maximize the chance of retrieving relevant information.

For each variant:
1. Maintain the core intent of the original question
2. Use different terminology, phrasings, or approaches (e.g., "batch number" vs "lot number")
3. Consider both broader and more specific formulations
4. Use domain-specific COA terminology (specifications, test results, acceptance criteria, etc.)

IMPORTANT: Respond ONLY with the rephrased questions, one per line, numbered. No explanations, no additional text.

Example:
Original: "What is the batch number?"
Response:
1. What is the lot number?
2. What is the batch identification code?
3. Which batch does this product belong to?
4. What is the manufacturing batch ID?
5. Can you provide the batch/lot identifier?"""

    async def rephrase(self, question: str) -> List[str]:
        """
        Rephrase a question into multiple search queries.

        Args:
            question: The original question to rephrase

        Returns:
            A list of rephrased questions
        """
        try:
            # Create messages for the LLM
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Original question: {question}")
            ]

            # Call LLM directly without ReAct agent
            response = await self.llm.ainvoke(messages)
            rephrased_text = response.content.strip()

            # Split into lines and clean up
            lines = rephrased_text.split('\n')
            cleaned_questions = []

            for line in lines:
                # Remove leading/trailing whitespace
                cleaned = line.strip()

                # Skip empty lines
                if not cleaned:
                    continue

                # Remove numbering (1. 2. 3. etc.)
                if cleaned and cleaned[0].isdigit():
                    # Find the first non-digit/non-dot/non-space character
                    for i, char in enumerate(cleaned):
                        if char not in '0123456789. ':
                            cleaned = cleaned[i:].strip()
                            break

                # Remove bullet points
                if cleaned.startswith('- '):
                    cleaned = cleaned[2:].strip()
                elif cleaned.startswith('* '):
                    cleaned = cleaned[2:].strip()

                # Only add non-empty, meaningful questions
                if cleaned and len(cleaned) > 5:
                    cleaned_questions.append(cleaned)

            # Always include the original question as fallback
            if question not in cleaned_questions:
                cleaned_questions.append(question)

            # Limit to 5 variations
            return cleaned_questions[:5]

        except Exception as e:
            # On any error, return original question
            print(f"QuestionRephraser error: {e}")
            return [question]
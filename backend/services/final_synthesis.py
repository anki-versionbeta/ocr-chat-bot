"""
Final Synthesis Agent Module - Phase 8 Enhancement

Different synthesis strategies for EXPLORATORY, EXHAUSTIVE, and VISUAL_AUDIT intents.
Filters irrelevant findings and produces focused, coherent answers.
"""

import os
import json
import logging
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .query_analyzer import QueryAnalysis, QueryType

logger = logging.getLogger(__name__)

# API Configuration
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED


@dataclass
class SynthesisResult:
    """Result from final synthesis."""
    answer: str
    relevant_findings: List[Dict]
    filtered_count: int  # How many findings were filtered out
    confidence: float
    cell_ids: List[str]


# =============================================================================
# EXPLORATORY SYNTHESIS AGENT
# =============================================================================

EXPLORATORY_SYNTHESIS_PROMPT = """You are a relevance filter and answer synthesizer for document Q&A.

## ORIGINAL USER QUERY
{query}

## QUERY ANALYSIS
- Query Type: {query_type}
- Focus Entities (MUST be in answer): {focus_entities}
- Anchor Term: {anchor_term}
- Target: {target_terms}
- Relevance Rule: {relevance_rule}

## ALL AGENT FINDINGS
{all_findings}

## YOUR CRITICAL TASK
1. **FILTER**: Remove any findings that DON'T directly answer the user's query
2. **FILTER**: If focus_entities are specified, remove findings that don't contain them
3. **SYNTHESIZE**: Combine remaining relevant findings into ONE coherent answer
4. **FORMAT**: Present as a clean, focused answer

## FILTERING RULES
- If user asked about "lot number X", ONLY include findings mentioning X
- If user asked "which page has Y", only include pages actually containing Y
- Remove duplicate information
- Remove tangential/unrelated findings

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
    "relevant_findings": [
        {{"finding": "text", "page": 1, "is_relevant": true, "reason": "contains focus entity"}},
        ...
    ],
    "synthesized_answer": "Your coherent answer here",
    "confidence": 0.9
}}

IMPORTANT: The synthesized_answer should ONLY contain information that directly answers the user's query.
If the user asked about a specific item, don't include information about other items.
"""


EXHAUSTIVE_SYNTHESIS_PROMPT = """You are a comprehensive data extractor for document Q&A.

## ORIGINAL USER QUERY
{query}

## QUERY ANALYSIS
- Target to Extract: {target_terms}
- Focus Entities: {focus_entities}

## ALL AGENT FINDINGS
{all_findings}

## YOUR TASK
1. **COLLECT**: Gather ALL instances of the target item from all findings
2. **DEDUPLICATE**: Remove exact duplicates
3. **FORMAT**: Present as a complete list
4. **VERIFY**: Ensure nothing is missed

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
    "all_items": ["item1", "item2", "item3"],
    "items_by_page": {{"page_1": ["item"], "page_2": ["item"]}},
    "synthesized_answer": "Complete list: item1, item2, item3...",
    "total_count": 5,
    "confidence": 0.9
}}

IMPORTANT: Extract ALL instances. Don't miss any.
"""


VISUAL_AUDIT_SYNTHESIS_PROMPT = """You are a verification specialist for document audit.

## ORIGINAL USER QUERY
{query}

## VERIFICATION TARGET
- What to Verify: {target_terms}
- Focus Entity: {anchor_term}
- Verification Rule: {relevance_rule}

## ALL AGENT FINDINGS
{all_findings}

## YOUR TASK
1. **ANALYZE**: Review all findings related to the verification target
2. **VERIFY**: Determine if the verification passes or fails
3. **EVIDENCE**: Cite specific evidence from findings
4. **CONCLUDE**: Provide clear yes/no answer with reasoning

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
    "verification_result": "PASS" or "FAIL" or "INCONCLUSIVE",
    "evidence": ["evidence1", "evidence2"],
    "issues_found": ["issue1"] or [],
    "synthesized_answer": "Verification result with explanation",
    "confidence": 0.9
}}
"""


def synthesize_exploratory(
    query: str,
    analysis: QueryAnalysis,
    agent_findings: List[Dict],
) -> SynthesisResult:
    """
    Synthesize exploratory query results - filter irrelevant findings.

    Args:
        query: Original user query
        analysis: Query analysis with focus entities
        agent_findings: List of findings from parallel agents

    Returns:
        SynthesisResult with filtered, coherent answer
    """
    try:
        # Format findings for prompt
        findings_text = _format_findings(agent_findings)

        prompt = EXPLORATORY_SYNTHESIS_PROMPT.format(
            query=query,
            query_type=analysis.query_type.value,
            focus_entities=analysis.focus_entities or "None specified",
            anchor_term=analysis.anchor_term or "None",
            target_terms=analysis.target_terms or "General information",
            relevance_rule=analysis.relevance_rule or "Include relevant findings",
            all_findings=findings_text
        )

        result = _call_synthesis_llm(prompt)

        if result:
            relevant = result.get("relevant_findings", [])
            answer = result.get("synthesized_answer", "")
            confidence = result.get("confidence", 0.8)

            # Extract cell_ids from relevant findings
            cell_ids = _extract_cell_ids_from_relevant(relevant, agent_findings)

            filtered_count = len(agent_findings) - len([r for r in relevant if r.get("is_relevant")])

            logger.info(f"Exploratory synthesis: {len(agent_findings)} findings -> "
                       f"{len(relevant)} relevant (filtered {filtered_count})")

            return SynthesisResult(
                answer=answer,
                relevant_findings=relevant,
                filtered_count=filtered_count,
                confidence=confidence,
                cell_ids=cell_ids
            )

        # Fallback: return combined findings without filtering
        return _fallback_synthesis(agent_findings)

    except Exception as e:
        logger.error(f"Exploratory synthesis error: {e}")
        return _fallback_synthesis(agent_findings)


def synthesize_exhaustive(
    query: str,
    analysis: QueryAnalysis,
    agent_findings: List[Dict],
) -> SynthesisResult:
    """
    Synthesize exhaustive query results - collect ALL instances.

    Args:
        query: Original user query
        analysis: Query analysis
        agent_findings: List of findings from parallel agents

    Returns:
        SynthesisResult with complete list of all items
    """
    try:
        findings_text = _format_findings(agent_findings)

        prompt = EXHAUSTIVE_SYNTHESIS_PROMPT.format(
            query=query,
            target_terms=analysis.target_terms or "all items",
            focus_entities=analysis.focus_entities or "None",
            all_findings=findings_text
        )

        result = _call_synthesis_llm(prompt)

        if result:
            answer = result.get("synthesized_answer", "")
            all_items = result.get("all_items", [])
            confidence = result.get("confidence", 0.8)

            # Collect all cell_ids from findings
            cell_ids = []
            for finding in agent_findings:
                cell_ids.extend(finding.get("cell_ids", []))

            logger.info(f"Exhaustive synthesis: found {len(all_items)} unique items")

            return SynthesisResult(
                answer=answer,
                relevant_findings=[{"items": all_items}],
                filtered_count=0,  # Exhaustive doesn't filter
                confidence=confidence,
                cell_ids=list(set(cell_ids))
            )

        return _fallback_synthesis(agent_findings)

    except Exception as e:
        logger.error(f"Exhaustive synthesis error: {e}")
        return _fallback_synthesis(agent_findings)


def synthesize_visual_audit(
    query: str,
    analysis: QueryAnalysis,
    agent_findings: List[Dict],
) -> SynthesisResult:
    """
    Synthesize visual audit results - verify and report issues.

    Args:
        query: Original user query
        analysis: Query analysis
        agent_findings: List of findings from parallel agents

    Returns:
        SynthesisResult with verification result
    """
    try:
        findings_text = _format_findings(agent_findings)

        prompt = VISUAL_AUDIT_SYNTHESIS_PROMPT.format(
            query=query,
            target_terms=analysis.target_terms or "verification target",
            anchor_term=analysis.anchor_term or "document",
            relevance_rule=analysis.relevance_rule or "verify correctness",
            all_findings=findings_text
        )

        result = _call_synthesis_llm(prompt)

        if result:
            answer = result.get("synthesized_answer", "")
            evidence = result.get("evidence", [])
            issues = result.get("issues_found", [])
            confidence = result.get("confidence", 0.8)

            # Collect cell_ids from findings
            cell_ids = []
            for finding in agent_findings:
                cell_ids.extend(finding.get("cell_ids", []))

            logger.info(f"Visual audit synthesis: result={result.get('verification_result')}, "
                       f"issues={len(issues)}")

            return SynthesisResult(
                answer=answer,
                relevant_findings=[{"evidence": evidence, "issues": issues}],
                filtered_count=0,
                confidence=confidence,
                cell_ids=list(set(cell_ids))
            )

        return _fallback_synthesis(agent_findings)

    except Exception as e:
        logger.error(f"Visual audit synthesis error: {e}")
        return _fallback_synthesis(agent_findings)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _call_synthesis_llm(prompt: str, timeout: int = 30) -> Optional[Dict]:
    """Call LLM for synthesis."""
    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "model": "claude-3.7-sonnet",  # Use Sonnet for better reasoning
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,  # Increased from 1500 to avoid truncation
            "temperature": 0.0
        }

        response = requests.post(
            f"{ILIAD_URL}/api/llm/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code != 200:
            logger.error(f"Synthesis LLM error: {response.status_code}")
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from response
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    except json.JSONDecodeError as e:
        logger.error(f"Synthesis JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"Synthesis LLM call error: {e}")
        return None


def _format_findings(agent_findings: List[Dict]) -> str:
    """Format agent findings for synthesis prompt."""
    formatted = []
    for i, finding in enumerate(agent_findings, 1):
        answer = finding.get("answer", "")
        pages = finding.get("pages", [])
        confidence = finding.get("confidence", 0)

        formatted.append(f"Finding {i} (pages: {pages}, confidence: {confidence}):\n{answer}\n")

    return "\n---\n".join(formatted)


def _extract_cell_ids_from_relevant(relevant: List[Dict], original_findings: List[Dict]) -> List[str]:
    """Extract cell_ids from relevant findings only."""
    cell_ids = []

    relevant_texts = set()
    for r in relevant:
        if r.get("is_relevant"):
            relevant_texts.add(r.get("finding", "").lower()[:100])

    for finding in original_findings:
        answer_preview = finding.get("answer", "").lower()[:100]
        # Check if this finding was marked as relevant
        for rel_text in relevant_texts:
            if rel_text in answer_preview or answer_preview in rel_text:
                cell_ids.extend(finding.get("cell_ids", []))
                break

    return list(set(cell_ids))


def _fallback_synthesis(agent_findings: List[Dict]) -> SynthesisResult:
    """Fallback when LLM synthesis fails - combine all findings."""
    answers = []
    cell_ids = []
    total_confidence = 0

    for finding in agent_findings:
        answer = finding.get("answer", "")
        if answer and "not found" not in answer.lower():
            # Clean up raw JSON that may have leaked through failed parsing
            cleaned_answer = _clean_raw_json_from_answer(answer)
            if cleaned_answer:
                answers.append(cleaned_answer)
                cell_ids.extend(finding.get("cell_ids", []))
                total_confidence += finding.get("confidence", 0)

    if answers:
        combined = "Based on the document, I found the following:\n\n"
        for i, ans in enumerate(answers, 1):
            combined += f"{i}. {ans}\n\n"
        avg_confidence = total_confidence / len(answers)
    else:
        combined = "I couldn't find relevant information in the document."
        avg_confidence = 0.0

    return SynthesisResult(
        answer=combined,
        relevant_findings=[],
        filtered_count=0,
        confidence=avg_confidence,
        cell_ids=list(set(cell_ids))
    )


def _clean_raw_json_from_answer(answer: str) -> str:
    """
    Clean up raw JSON that may have leaked through when agent response parsing failed.

    Handles cases where the answer contains:
    - ```json {...} ``` blocks
    - Raw JSON objects starting with { and ending with }
    - Mixed content with JSON at the beginning or end
    """
    if not answer:
        return answer

    # Check if answer starts with JSON-like content
    stripped = answer.strip()

    # If it's a pure JSON object, try to extract the 'answer' field
    if stripped.startswith('{') and stripped.endswith('}'):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and 'answer' in parsed:
                return parsed['answer']
        except json.JSONDecodeError:
            pass

    # Check for ```json blocks
    if '```json' in answer:
        import re
        # Try to extract answer from JSON block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', answer, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict) and 'answer' in parsed:
                    # Return the answer field from JSON
                    return parsed['answer']
            except json.JSONDecodeError:
                pass

        # If JSON parsing fails, remove the JSON block entirely
        cleaned = re.sub(r'```json\s*\{.*?\}\s*```', '', answer, flags=re.DOTALL).strip()
        if cleaned:
            return cleaned

    # Check for mixed content: text followed by raw JSON
    if '\n{' in answer or answer.endswith('}'):
        import re
        # Remove trailing JSON object
        cleaned = re.sub(r'\n?\{[^{}]*"answer"[^{}]*\}$', '', answer, flags=re.DOTALL).strip()
        if cleaned and cleaned != answer:
            return cleaned

    return answer


# =============================================================================
# MAIN SYNTHESIS FUNCTION
# =============================================================================

def synthesize_agent_results(
    query: str,
    analysis: QueryAnalysis,
    agent_findings: List[Dict],
    intent_type: str
) -> SynthesisResult:
    """
    Main entry point for final synthesis.

    Routes to appropriate synthesis strategy based on intent type.

    Args:
        query: Original user query
        analysis: Query analysis with focus entities
        agent_findings: List of findings from parallel agents
        intent_type: "exploratory", "exhaustive", or "visual_audit"

    Returns:
        SynthesisResult with filtered, coherent answer
    """
    logger.info(f"Final synthesis: intent={intent_type}, findings={len(agent_findings)}")

    if intent_type == "exhaustive":
        return synthesize_exhaustive(query, analysis, agent_findings)
    elif intent_type == "visual_audit":
        return synthesize_visual_audit(query, analysis, agent_findings)
    else:
        # Default to exploratory synthesis (also used for conditional queries)
        return synthesize_exploratory(query, analysis, agent_findings)

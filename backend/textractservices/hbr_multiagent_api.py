"""
API wrapper for HBR Multi-Agent System
Provides FastAPI integration for the Claude-powered multi-agent HBR document processing
"""
import os
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Import the multi-agent functions
try:
    from .hbr_multiagent import (
        run_claude_multiagent,
        process_user_feedback,
        GraphState,
        excel_to_json_string
    )
except ImportError:
    try:
        from textractservices.hbr_multiagent import (
            run_claude_multiagent,
            process_user_feedback,
            GraphState,
            excel_to_json_string
        )
    except ImportError:
        # Last resort - import from current directory
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.append(current_dir)
        from hbr_multiagent import (
            run_claude_multiagent,
            process_user_feedback,
            GraphState,
            excel_to_json_string
        )

class HBRMultiAgentSession:
    """
    Session manager for HBR multi-agent processing
    Maintains state across multiple API calls for feedback and reprocessing
    """
    
    def __init__(self, session_id: str, pdf_path: str, excel_path: str):
        self.session_id = session_id
        self.pdf_path = pdf_path
        self.excel_path = excel_path
        self.created_at = datetime.now()
        self.state: Optional[GraphState] = None
        self.results: List[Dict] = []
        self.missing_parameters: List[Dict] = []
        self.processing_complete = False
        # Add progress tracking
        self.progress_callback = None
        self.current_progress = 0
        self.current_stage = "initializing"
        
    def set_progress_callback(self, callback):
        """Set the progress callback function"""
        self.progress_callback = callback
        
    def update_progress(self, stage: str, progress: int, message: str):
        """Update progress for this session"""
        self.current_stage = stage
        self.current_progress = progress
        if self.progress_callback:
            self.progress_callback(progress, message)
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for JSON serialization"""
        return {
            "session_id": self.session_id,
            "pdf_path": self.pdf_path,
            "excel_path": self.excel_path,
            "created_at": self.created_at.isoformat(),
            "processing_complete": self.processing_complete,
            "results_count": len(self.results),
            "missing_parameters_count": len(self.missing_parameters)
        }

class HBRMultiAgentAPI:
    """
    API wrapper for the HBR Multi-Agent System
    Handles session management and provides FastAPI-compatible endpoints
    """
    
    def __init__(self):
        self.sessions: Dict[str, HBRMultiAgentSession] = {}
        self.executor = ThreadPoolExecutor(max_workers=2)
        
    def create_session(self, pdf_path: str, excel_path: str) -> str:
        """Create a new multi-agent processing session"""
        session_id = str(uuid.uuid4())
        session = HBRMultiAgentSession(session_id, pdf_path, excel_path)
        self.sessions[session_id] = session
        return session_id
    
    def get_session(self, session_id: str) -> Optional[HBRMultiAgentSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    async def process_documents(self, session_id: str, output_dir: str) -> Dict[str, Any]:
        """
        Process HBR documents using the multi-agent system
        
        Args:
            session_id: Session identifier
            output_dir: Directory to save output files
            
        Returns:
            Dictionary with processing results
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            # Run the multi-agent system in thread pool to avoid blocking
            final_state = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                run_claude_multiagent,
                session.pdf_path,
                session.excel_path,
                session.progress_callback  # Pass the progress callback
            )
            
            # Store the final state in session
            session.state = final_state
            session.processing_complete = True
            
            # Parse the final results
            if "final_results" in final_state and final_state["final_results"]:
                try:
                    # Try to parse JSON from final results
                    final_output = json.loads(final_state["final_results"])
                    session.results = final_output.get("final_results", [])
                    session.missing_parameters = final_output.get("still_missing", [])
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract from agent decisions
                    session.results = self._extract_results_from_decisions(final_state)
                    session.missing_parameters = []
            else:
                session.results = self._extract_results_from_decisions(final_state)
                session.missing_parameters = []
            
            # Use the Excel file path from the state if available
            if "output_excel_path" in final_state and final_state["output_excel_path"]:
                excel_output_path = final_state["output_excel_path"]
            else:
                # Fallback: Save results to Excel if not already saved
                excel_output_path = await self._save_results_to_excel(session, output_dir)
            
            # Create response
            return {
                "success": True,
                "session_id": session_id,
                "results": session.results,
                "missing_parameters": session.missing_parameters,
                "excel_file_path": excel_output_path,
                "processing_summary": {
                    "total_parameters": len(session.results),
                    "successfully_extracted": len([r for r in session.results if r.get("value")]),
                    "missing_parameters": len(session.missing_parameters),
                    "extraction_rate": f"{(len([r for r in session.results if r.get('value')]) / max(1, len(session.results))) * 100:.1f}%"
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "session_id": session_id
            }
    
    async def handle_feedback(
        self, 
        session_id: str, 
        missing_parameter: str, 
        user_message: str,
        pages_already_checked: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Handle user feedback for missing parameters
        
        Args:
            session_id: Session identifier
            missing_parameter: Name of the missing parameter
            user_message: User's message about the missing parameter
            pages_already_checked: List of pages already checked (optional)
            
        Returns:
            Dictionary with assistant's response and recommendations
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.processing_complete:
            return {
                "success": False,
                "error": "Initial processing not complete. Please wait for processing to finish."
            }
        
        # Parse user message to extract page number if mentioned
        import re
        page_match = re.search(r'page\s*(\d+)', user_message.lower())
        expected_page = int(page_match.group(1)) if page_match else 1
        
        print(f"\n[API] Processing feedback for '{missing_parameter}'")
        print(f"[API] User message: {user_message}")
        print(f"[API] Detected page: {expected_page}")
        
        try:
            # Call the feedback function
            feedback_response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                process_user_feedback,
                session.pdf_path,
                session.excel_path,
                missing_parameter,
                "missing",  # issue_type
                expected_page,
                None,  # current_value
                user_message,  # hint
                session.state
            )
            
            # Check if the response was successful
            if feedback_response.get("status") == "success":
                feedback_data = feedback_response["feedback_processed"]
                return {
                    "success": True,
                    "session_id": session_id,
                    "parameter": missing_parameter,
                    "assistant_response": feedback_data.get("assistant_message", "I'll help you find that parameter."),
                    "recommendations": feedback_data.get("recommendations", {}),
                    "next_steps": "Click 'Reprocess' to search these pages with the provided guidance."
                }
            else:
                return {
                    "success": False,
                    "error": feedback_response.get("error", "Unknown error occurred"),
                    "session_id": session_id
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "session_id": session_id
            }


    # Fixed reprocess_with_hint method with proper state management
    async def reprocess_with_hint(
        self, 
        session_id: str, 
        parameter: str, 
        user_hint: str,
        recommended_pages: List[int]
    ) -> Dict[str, Any]:
        """
        Reprocess a specific parameter with user's hint
        
        Args:
            session_id: Session identifier
            parameter: Parameter to reprocess
            user_hint: User's specific hint about where to find the parameter
            recommended_pages: Pages to check based on feedback
            
        Returns:
            Dictionary with reprocessing results
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.state:
            return {
                "success": False,
                "error": "No processing state available for reprocessing"
            }
        
        try:
            print(f"\n[API] Reprocessing '{parameter}' on pages {recommended_pages}")
            print(f"[API] Using hint: {user_hint}")
            
            # Create a state for the feedback workflow
            feedback_state = dict(session.state)  # Copy existing state
            
            # Add the user feedback request to state
            feedback_state["user_feedback_request"] = {
                "parameter": parameter,
                "missing_parameter": parameter,  # Both formats for compatibility
                "issue_type": "missing",
                "original_pages_checked": [],
                "user_message": user_hint,
                "expected_page": recommended_pages[0] if recommended_pages else 1
            }
            
            # Add a mock feedback decision to trigger reprocessing
            if "agent_decisions" not in feedback_state:
                feedback_state["agent_decisions"] = []
                
            feedback_state["agent_decisions"].append({
                "agent": "feedback",
                "interaction": {
                    "user_request": {
                        "missing_parameter": parameter,
                        "original_pages_checked": [],
                        "user_message": user_hint
                    },
                    "pages_to_recheck": recommended_pages,
                    "user_final_hint": user_hint
                }
            })
            
            # Fix the import - use the same pattern as at the top of the file
            try:
                from .hbr_multiagent import reprocessing_agent
            except ImportError:
                try:
                    from textractservices.hbr_multiagent import reprocessing_agent
                except ImportError:
                    # Last resort - import from current directory
                    import sys
                    import os
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    sys.path.append(current_dir)
                    from hbr_multiagent import reprocessing_agent
            
            # Run reprocessing agent
            updated_state = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                reprocessing_agent,
                feedback_state
            )
            
            # Update session state
            session.state = updated_state
            
            # Extract reprocessing results
            reprocessing_results = []
            if updated_state["agent_decisions"]:
                # Look for the most recent reprocessing decision
                for decision in reversed(updated_state["agent_decisions"]):
                    if decision.get("agent") == "reprocessing":
                        reprocessing_results = decision.get("results", [])
                        break
            
            # Update session results if parameter was found
            if reprocessing_results:
                # Remove old result for this parameter if it exists
                session.results = [r for r in session.results if r.get("parameter") != parameter]
                # Add new result
                for result in reprocessing_results:
                    session.results.append({
                        "parameter": result.get("parameter"),
                        "page": result.get("page"),
                        "value": result.get("value"),
                        "unit": result.get("unit", ""),
                        "location": result.get("location_found", "")
                    })
                # Remove from missing parameters
                session.missing_parameters = [p for p in session.missing_parameters if p.get("parameter") != parameter]
                
                message = f"Found {parameter}: {reprocessing_results[0]['value']} {reprocessing_results[0].get('unit', '')}"
                if reprocessing_results[0].get('location_found'):
                    message += f" (Location: {reprocessing_results[0]['location_found']})"
            else:
                message = f"Parameter '{parameter}' still not found on recommended pages {recommended_pages}"
            
            return {
                "success": True,
                "session_id": session_id,
                "parameter": parameter,
                "found": len(reprocessing_results) > 0,
                "results": reprocessing_results,
                "message": message,
                "pages_checked": recommended_pages
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "session_id": session_id
            }
    
    def _extract_results_from_decisions(self, final_state: GraphState) -> List[Dict]:
        """Extract results from agent decisions if final_results parsing fails"""
        results = []
        
        # Look for worker results in agent decisions
        for decision in final_state.get("agent_decisions", []):
            if decision.get("agent") == "parallel_workers":
                worker_results = decision.get("results", [])
                results.extend(worker_results)
            elif decision.get("agent") == "reprocessing":
                reprocessing_results = decision.get("results", [])
                results.extend(reprocessing_results)
        
        return results
    
    async def _save_results_to_excel(self, session: HBRMultiAgentSession, output_dir: str) -> str:
        """Save session results to Excel file"""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Extract original filename from PDF path
        original_filename = os.path.splitext(os.path.basename(session.pdf_path))[0]
        
        # Create filename with original name
        filename = f"{original_filename}_hbr_results_{timestamp}.xlsx"
        output_path = os.path.join(output_dir, filename)
        
        # Create DataFrame from results
        if session.results:
            df = pd.DataFrame(session.results)
        else:
            # Create empty DataFrame with expected columns
            df = pd.DataFrame(columns=["parameter", "page", "value", "unit", "confidence"])
        
        # Save to Excel with proper sheet name
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='HBR Results', index=False)
        
        return output_path
    
    def cleanup_session(self, session_id: str) -> bool:
        """Remove session from memory"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        session = self.get_session(session_id)
        if session:
            return session.to_dict()
        return None
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions"""
        return [session.to_dict() for session in self.sessions.values()]

# Global instance
hbr_multiagent_api = HBRMultiAgentAPI() 
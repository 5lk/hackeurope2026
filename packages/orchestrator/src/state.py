from typing import Annotated, Any, Dict, List, Optional, TypedDict
import operator

class FilePlan(TypedDict):
    files: List[str]
    notes: List[str]

class HandoffData(TypedDict):
    task_id: str
    summary: str
    artifacts: List[str]

class ArchitectResult(TypedDict):
    file_plan: FilePlan
    interfaces: Dict[str, str]
    raw_response: str

class SWEResult(TypedDict):
    target_file: str
    summary: str
    code_snippet: str

class SWEWorkerState(TypedDict):
    target_file: str
    architecture_plan: ArchitectResult
    user_prompt: str
    manager_plan: str
    fix_instructions: str

class QAResult(TypedDict):
    passed: bool
    feedback: Optional[str]

class GraphState(TypedDict):
    # Inputs
    user_prompt: str
    
    # Global state managed through conversation/execution
    messages: Annotated[list, operator.add]
    
    # Manager
    manager_plan: str
    department_route: str
    
    # Architect
    architecture_plan: Optional[ArchitectResult]
    files_to_implement: List[str]
    
    # SWE (Recursive workers)
    # the swe results will be appended by multiple SWE nodes running in parallel
    swe_results: Annotated[List[SWEResult], operator.add]
    
    # QA 
    qa_results: Annotated[List[QAResult], operator.add]
    
    # Terminal routing feedback
    requires_fixes: bool
    fix_instructions: str

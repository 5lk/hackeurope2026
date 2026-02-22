from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from typing import Literal
from packages.orchestrator.src.state import GraphState, SWEWorkerState
from packages.orchestrator.src.nodes.manager import manager_node
from packages.orchestrator.src.nodes.architect import architect_node
from packages.orchestrator.src.nodes.swe_group import swe_worker_node
from packages.orchestrator.src.nodes.qa import qa_node

# Routing functions
def route_after_manager(state: GraphState) -> Literal["architect", "__end__"]:
    route = state.get("department_route", "architect")
    if route == "architect":
        return "architect"
    return "__end__"

def assign_swe_workers(state: GraphState):
    """
    This is the Map function that spawns recursive SWE workers.
    It returns a list of Send objects, dispatching parallel nodes.
    """
    files_to_implement = state.get("files_to_implement", [])
    
    # Send allows parallel execution of the `swe_worker` node
    return [
        Send(
            "swe_worker",
            SWEWorkerState(
                target_file=f,
                architecture_plan=state.get("architecture_plan", {}), # type: ignore
                user_prompt=state.get("user_prompt", ""),
                manager_plan=state.get("manager_plan", ""),
                fix_instructions=state.get("fix_instructions", "")
            )
        )
        for f in files_to_implement
    ]

def route_after_qa(state: GraphState) -> Literal["swe_supervisor", "__end__"]:
    qa_results = state.get("qa_results", [])
    if len(qa_results) >= 15:
        print("Max revisions reached. Stopping.")
        return "__end__"
        
    if state.get("requires_fixes", False):
        print("QA returned fixes. Rerouting to SWEs.")
        return "swe_supervisor"
    return "__end__"
    
# Actually just need a dummy node to act as the fan-out point
def swe_supervisor_node(state: GraphState) -> dict:
    return {} # Does nothing, the magic is in the conditional edges

def build_graph() -> StateGraph:
    builder = StateGraph(GraphState)
    
    # Add nodes
    builder.add_node("manager", manager_node)
    builder.add_node("architect", architect_node)
    builder.add_node("swe_supervisor", swe_supervisor_node)
    builder.add_node("swe_worker", swe_worker_node)
    builder.add_node("qa", qa_node)
    
    # Add edges
    builder.add_edge(START, "manager")
    
    # Route to either the architect or END if it's not a dev request
    builder.add_conditional_edges("manager", route_after_manager)
    
    builder.add_edge("architect", "swe_supervisor")
    
    # Fan out to dynamic SWE workers
    builder.add_conditional_edges("swe_supervisor", assign_swe_workers, ["swe_worker"])
    
    # Fan in from all SWE workers to QA
    builder.add_edge("swe_worker", "qa")
    
    # Loop back if QA rejects
    builder.add_conditional_edges("qa", route_after_qa)
    
    return builder.compile()

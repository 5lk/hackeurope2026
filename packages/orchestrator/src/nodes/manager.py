import json
from langchain_core.messages import HumanMessage
from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.orchestrator.src.state import GraphState

def manager_node(state: GraphState) -> dict:
    llm = LLMClient(model="gemini-2.5-pro", temperature=0)
    system_prompt = "You are the manager and strategic router. You decompose work and decide if a task needs coding."
    
    prompt = f"""
Decompose the work for this user request into high-level phases.
User Request: {state['user_prompt']}

CRITICAL CONSTRAINTS:
1. Do not include or require any binary assets like images (.png, .jpg) or audio (.wav, .mp3). Use text-based alternatives like ASCII art or emojis instead.
2. Do not use or plan for any external APIs unless the user explicitly provided one or requested it. Mock data or use local generation instead.
3. TEST-DRIVEN DEVELOPMENT (TDD): You must design the plan such that every component has an accompanying unit test (e.g., using `pytest` or `unittest`). 
4. Focus entirely on pure, testable, and robust code solutions.

Return a JSON with keys:
- "plan": detailed strategy
- "route": either "architect" (needs coding) or "end" (just a question)
    """
    
    try:
        data = llm.generate_json(prompt, system_prompt=system_prompt)
        
        return {
            "manager_plan": data.get("plan", ""),
            "department_route": data.get("route", "architect"),
            "messages": [HumanMessage(content=f"Manager Plan: {data.get('plan')}")]
        }
    except Exception as e:
        print(f"Manager Exception: {e}")
        return {
            "manager_plan": "Failed to parse plan. Proceeding to architect.",
            "department_route": "architect",
        }

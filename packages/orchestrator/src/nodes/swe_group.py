from langchain_core.messages import HumanMessage
from packages.core.src.llm_client import LLMClient
from packages.orchestrator.src.state import SWEWorkerState, SWEResult
from langgraph.constants import Send

def swe_worker_node(state: SWEWorkerState) -> dict:
    llm = LLMClient(model="gemini-2.5-flash", temperature=0)
    
    target_file = state["target_file"]
    arch_plan = state.get("architecture_plan", {})
    interfaces = arch_plan.get("interfaces", {}).get(target_file, "No specific interface provided.")
    
    system_prompt = "You are a Software Engineer Worker. Output only the exact raw code for the requested file, formatted in markdown."
    feedback_section = ""
    if state.get("fix_instructions"):
        feedback_section = f"\nQA rejected your previous attempt with this feedback:\n{state['fix_instructions']}\n\nYou must fix these issues in your code."

    prompt = f"""
Your task is to implement the following specific file: {target_file}

User Prompt: {state.get('user_prompt')}
Manager Plan: {state.get('manager_plan')}

Architect Guidelines for your file:
{interfaces}{feedback_section}

Please return the raw code that belongs in this file. Provide a brief summary as well.
Use markdown code blocks, e.g., ```python ... ```
    """
    
    response = llm.generate(prompt, system_prompt=system_prompt)
    
    # Extract code
    import re
    content = response.text
    
    # Try to extract from ```python ... ``` or just ``` ... ``` block
    match = re.search(r'```(?:python)?\s*(.*?)\s*```', content, re.DOTALL)
    if match:
        code_snippet = match.group(1)
    else:
        # Sometimes models forget the trailing backticks if they get cut off
        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                code_snippet = parts[1]
                if code_snippet.startswith("python\n"):
                    code_snippet = code_snippet[7:]
        else:
            # Fallback
            code_snippet = content

    swe_result: SWEResult = {
        "target_file": target_file,
        "summary": "Completed implementation.",
        "code_snippet": code_snippet.strip()
    }
    
    # In map-reduce, the return dict merges into the global state's Annotated reducers
    return {
        "swe_results": [swe_result],
        "messages": [HumanMessage(content=f"SWE finished {target_file}")]
    }

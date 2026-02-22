import json
from langchain_core.messages import HumanMessage
from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.orchestrator.src.state import GraphState, ArchitectResult

def architect_node(state: GraphState) -> dict:
    llm = LLMClient(model="gemini-2.5-pro", temperature=0)
    system_prompt = "You are the Architect. You design the specific file structure required for the task."
    
    prompt = f"""
Manager's Plan:
{state['manager_plan']}

Create an architecture design. You must specify the list of exact files to implement. 

CRITICAL CONSTRAINTS:
1. ONLY design Python source code files (.py), text files (.txt, .md), or standard config files.
2. ABSOLUTELY DO NOT ask for images (.png, .jpg), audio (.wav, .mp3), or any other binary assets.
3. If the plan implies graphics or audio, you MUST use text-based alternatives (like ASCII, emojis) or simply omit audio.
4. DO NOT design any integrations with external APIs unless explicitly requested by the user.
5. OPTIMIZE FOR SPEED AND ACCURACY: Minimize the number of files. For simple games or endpoints, try to fit everything into just 1 to 3 files (e.g., `main.py`, `config.py`). Do not over-engineer with excessive modularity, as it breaks parallel SWE consistency.

Return valid JSON with the following structure:
{{
    "file_plan": {{
        "files": ["list", "of", "relative/file/paths.py"],
        "notes": ["list", "of", "design", "notes"]
    }},
    "interfaces": {{
        "file_path.py": "Description of classes/functions for this file"
    }}
}}
    """
    
    try:
        data = llm.generate_json(prompt, system_prompt=system_prompt)
        content = str(data)
        
        file_plan = data.get("file_plan", {"files": [], "notes": []})
        interfaces = data.get("interfaces", {})
        
        arch_result: ArchitectResult = {
            "file_plan": file_plan,
            "interfaces": interfaces,
            "raw_response": content
        }
        
        return {
            "architecture_plan": arch_result,
            "files_to_implement": file_plan.get("files", []),
            "messages": [HumanMessage(content=f"Architect designed {len(file_plan.get('files', []))} files.")]
        }
    except Exception as e:
        print(f"Architect Exception: {e}")
        # Fallback empty state
        return {
            "files_to_implement": [],
            "messages": [HumanMessage(content="Architect failed to generate a valid design.")]
        }

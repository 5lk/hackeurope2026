import argparse
import os
import sys
from dotenv import load_dotenv

from packages.orchestrator.src.graph import build_graph
from packages.orchestrator.src.state import GraphState

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LangGraph multi-agent system.")
    parser.add_argument("prompt", type=str, help="User prompt.")
    return parser.parse_args()

def main() -> None:
    args = _parse_args()
    load_dotenv()
    
    print("Compiling LangGraph application...")
    graph = build_graph()
    
    initial_state = GraphState(
        user_prompt=args.prompt,
        messages=[],
        manager_plan="",
        department_route="",
        architecture_plan=None,
        files_to_implement=[],
        swe_results=[],
        qa_results=[],
        requires_fixes=False,
        fix_instructions=""
    )
    
    print(f"Starting execution for prompt: '{args.prompt}'")
    
    # Run the graph
    print("Executing LangGraph (this might take a few minutes)...")
    final_state = initial_state
    
    last_processed_count = 0
    
    try:
        for state in graph.stream(initial_state, stream_mode="values"):
            final_state = state
            if state.get("messages"):
                print(f"--- Node Progress ---")
                print(state["messages"][-1].content)
            
            # Progressively save files as they are generated
            swe_results = state.get("swe_results", [])
            if len(swe_results) > last_processed_count:
                last_processed_count = len(swe_results)
                latest_files = {}
                for res in swe_results:
                    latest_files[res["target_file"]] = res["code_snippet"]
                
                for file_path, code in latest_files.items():
                    clean_path = file_path.lstrip("/\\")
                    if ":" in clean_path:
                        clean_path = clean_path.split(":", 1)[-1].lstrip("/\\")
                        
                    safe_path = os.path.join(os.getcwd(), "output", clean_path)
                    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                    
                    with open(safe_path, "w", encoding="utf-8") as f:
                        f.write(code)
    except KeyboardInterrupt:
        print("\n\nExecution was manually interrupted (Ctrl+C). Progressive files have been saved to output/.")
                
    print("\n--- Execution Complete ---")
    
    # Save the files to disk
    swe_results = final_state.get("swe_results", [])
    if swe_results:
        print(f"\nWriting {len(swe_results)} files to disk in output/ directory...")
        # Since QA can loop and append, we only want the LATEST version of each file.
        latest_files = {}
        for res in swe_results:
            latest_files[res["target_file"]] = res["code_snippet"]
            
        for file_path, code in latest_files.items():
            # Force all output to go into an output/ folder to prevent overwriting our own files
            # Strip any leading slashes or drive letters to ensure path is strictly relative
            clean_path = file_path.lstrip("/\\")
            if ":" in clean_path:
                clean_path = clean_path.split(":", 1)[-1].lstrip("/\\")
                
            safe_path = os.path.join(os.getcwd(), "output", clean_path)
            
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Saved: {safe_path} (length: {len(code)})")
    else:
        print("\nNo files were generated.")

if __name__ == "__main__":
    main()

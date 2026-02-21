# The Final Prompt — Multi-Department Agent Orchestrator (Python + Gemini)

This project implements a **multi-department, recursive agent orchestration system** in Python, powered by the Gemini API. It simulates three coordinated departments—Architecture, Implementation, and Testing—under a top-level Manager that plans and routes tasks with dependency tracking.

## Core Idea

You give **one prompt** to build a fully functioning MVP of any app or game.  
The system uses a hierarchical tree of agents that behaves like a real development org:

- **Manager**: strategic router, decomposes the prompt into domain tasks  
- **Architect**: designs interfaces, contracts, and module boundaries  
- **SWE**: implements code that strictly follows architecture contracts  
- **QA**: writes tests and drives coverage targets  

**Important constraint:** The generated MVPs must **not** use APIs that require keys.

---

## Features

- **Task domains**: architecture, implementation, testing, integration  
- **Dependency graph** via `dependsOn[]`  
- **Recursive decomposition** per department  
- **Domain-aware routing**  
- **Gemini-backed role prompts**  
- **Stubbed sandbox runners** (placeholders for real tool execution)

---

## Project Structure

```
packages/
├── core/src/
│   ├── llm_client.py          # Gemini wrapper
│   ├── types.py               # Task / Handoff types
│   └── task_domain.py         # Domain helpers
│
├── orchestrator/src/
│   ├── manager.py             # Top-level planner
│   ├── architect.py           # Architecture lead
│   ├── swe.py                 # Implementation lead
│   ├── qa.py                  # Testing lead
│   ├── department_router.py   # Domain router
│   ├── task_queue.py          # DependsOn enforcement
│   ├── reconciler.py          # Domain-aware fix routing (stub)
│   └── orchestrator.py        # System wiring
│
├── sandbox/src/
│   ├── swe_worker_runner.py   # SWE worker stub
│   └── qa_worker_runner.py    # QA worker stub
│
prompts/
├── manager.md
├── architect.md
├── architect-instance.md
├── swe.md
├── swe-worker.md
├── qa.md
└── qa-worker.md
```

---

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Set your Gemini API key:
```
export GEMINI_API_KEY="YOUR_KEY"
```

---

## Usage

Run the orchestrator from the repo root:

```
python main.py "Build an MVP for The Final Prompt platform"
```

Optional flags:

- `--model` to specify Gemini model
- `--prompts-dir` to override prompts folder

---

## Notes

This is a **full system scaffold** that matches the design described.  
The sandbox execution layer is **stubbed**; you can integrate real tool execution later.

If you want:
- real code editing,
- sandboxed execution,
- git commit flows,
- coverage measurement,

you can extend the runner stubs in `packages/sandbox/src/`.

---

## Hackathon Idea (Context)

**The Final Prompt** is a platform where users give one prompt to generate a complete MVP.  
This system simulates a real org using recursive agents and can evolve into the core engine for that platform.

---

## License

MIT (add your preferred license if needed).
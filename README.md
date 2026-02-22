# The Final Prompt

A one‑prompt generation interface: capture a single conversation and turn it into a complete, user‑defined app output.

## How to run

### Backend
```/dev/null/commands.txt#L1-2
python -m engine.server
or
uvicorn engine.server:app
```

### Frontend
```/dev/null/commands.txt#L4-5
npm install
npm run dev
```

## Usage

1. Start the backend (`python -m engine.server` or `uvicorn engine.server:app`).
2. Start the frontend (`npm install` then `npm run dev`).
3. Open the app in your browser.
4. Click the mic button to begin a conversation.
5. Click **Finish Conversation** to view the transcript in **Project Specification**.
6. Visualize the workflow.
7. Open the generated app from the output folder when it auto-opens in your file explorer.

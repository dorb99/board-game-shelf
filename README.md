# Board Games Library

A shared shelf of board games for a group of friends. No login: open the site, add a
game by name, say who owns it, and browse everyone's shelves. Each game has a rules
assistant powered by Gemini with Google Search.

## Setup

Requires Python 3.12+ and Node 20+.

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then fill in the keys

# Frontend
cd ..\frontend
npm install
```

Keys in `backend/.env`:

| Variable | What it is for | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | Rules assistant, and game lookup when BoardGameGeek has no match | https://aistudio.google.com/apikey |
| `BGG_API_TOKEN` | Game search, covers, player counts and play time | https://boardgamegeek.com/applications |
| `GEMINI_MODEL` | Optional. Defaults to `gemini-flash-latest` | |

The app runs without either key: games can then be added by hand with a link to a
cover image, and the rules assistant is unavailable.

## Run for development

Two terminals:

```powershell
cd backend;  .venv\Scripts\uvicorn app.main:app --reload
cd frontend; npm run dev
```

Open http://localhost:5173. Vite forwards `/api` and `/media` to the backend on port 8000.

## Run as one service

```powershell
cd frontend; npm run build
cd ..\backend; .venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The backend serves the built frontend, so the whole app is at http://localhost:8000.

## Deploy

The `Dockerfile` builds that single service. On a host such as Render, Fly.io or Railway:

1. Deploy the repository as a Docker service.
2. Attach a persistent disk mounted at `/data` (the SQLite database and cover images live there).
3. Set `GEMINI_API_KEY` and `BGG_API_TOKEN` as environment variables.

Run a single instance: the database is a local SQLite file.

Anyone with the URL can add, edit and remove games. The lookup and rules-assistant
endpoints are rate limited per IP address to protect the Gemini quota.

## Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest
cd frontend; npm test
```

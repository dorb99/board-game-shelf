# Board Games Library

A shared shelf of board games for a group of friends. No login: open the site, add a
game by name, check what was found, say who owns it, and browse everyone's shelves. Each game has a rules
assistant that searches the web, powered by Gemini or OpenAI.

## Setup

Requires Python 3.12+ and Node 20+.

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then fill in the key

# Frontend
cd ..\frontend
npm install
```

Settings in `backend/.env`:

| Variable | What it is for |
|---|---|
| `LLM_PROVIDER` | Which AI service looks games up and answers rules questions: `gemini` (default) or `openai` |
| `GEMINI_API_KEY` | Used when the provider is `gemini`. Get one at https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | Optional. Defaults to `gemini-flash-latest` |
| `OPENAI_API_KEY` | Used when the provider is `openai`. Get one at https://platform.openai.com/api-keys |
| `OPENAI_MODEL` | Optional. Defaults to `gpt-5-mini`; any model that supports the web search tool |
| `DATA_DIR` | Optional. Where the database, covers and game catalog live. Defaults to `backend/data`; a relative path is taken from the project root |

### Game catalog

Game names are matched against BoardGameGeek's ranks export, a CSV of every game with
its id, name and year. Download it from https://boardgamegeek.com/data_dumps/bg_ranks
(needs a BGG login), unzip it, and put `boardgames_ranks.csv` in the data directory
(`backend/data/boardgames_ranks.csv`). Replace the file and restart to refresh it.

Adding a game works like this:

1. The name is searched in the catalog. A game that is not there is searched on the web by the AI provider.
2. For the match you pick, the AI provider searches the web for the cover, player count and play time.
3. You review and correct everything, then add it.

If the provider refuses web search (for example a Gemini key without billing), it
answers from its own knowledge instead, the app says so, and no cover is fetched.

Without the catalog file every search goes to the AI provider. Without an API key, games can
still be added with the details and a cover image link typed in by hand, and the rules
assistant is unavailable.

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

The `Dockerfile` builds that single service: the React app, the API and the SQLite
database in one container. The database, cover images and game catalog live in `/data`.

To try the image locally (needs Docker):

```powershell
docker compose up --build
```

The app is at http://localhost:8080 (set `APP_PORT` for another port). Keys are read from
`backend/.env`, and the data is kept in the `library-data` volume. To add the catalog:

```powershell
docker compose cp backend/data/boardgames_ranks.csv app:/data/
docker compose restart
```

On Render, choose New > Blueprint and pick this repository; `render.yaml` sets up the
service and its disk, and asks for the API keys. On another host such as Fly.io or Railway:

1. Deploy the repository as a Docker service.
2. Attach a persistent disk mounted at `/data`.
3. Set `LLM_PROVIDER` and the matching API key as environment variables.

Then upload `boardgames_ranks.csv` to `/data` on the disk and restart. Without a
persistent disk the library is lost on every restart or redeploy.

Run a single instance: the database is a local SQLite file.

Anyone with the URL can add, edit and remove games. The lookup and rules-assistant
endpoints are rate limited per IP address to protect the API quota.

## Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest
cd frontend; npm test
```

# Sample Forge

Model‑agnostic desktop app for configuring and benchmarking local LLM servers (e.g., llama.cpp), exploring API parameters, converting/evaluating datasets, and running automated parameter search.

## Highlights
- Server Config: Build and launch a local `llama-server` with validated flags.
- API Parameters: Toggle and preview OpenAI‑style request payloads; quick, unified chat/text tests.
- Dataset Conversion: Browse LiveBench categories/subcategories and export to the app’s text format.
- Run Benchmark: Execute runs against exported datasets; store reproducible metadata and results.
- Scoring & Analysis: Inspect completed runs and summary stats.
- Auto Mode: Automated parameter exploration using bandit/ACO strategies; persists to SQLite.
- ACO Data Viewer: Explore optimization run databases and outcomes.

## Requirements
- OS: Windows 10/11 (primary), macOS/Linux supported for Python/Tkinter flows.
- Python: 3.11 – 3.13 (3.13 validated).
- Internet:
  - First run installs Python packages into a virtual environment.
  - Dataset Conversion loads LiveBench data from Hugging Face Hub.
- For Linux: install Tkinter (e.g., `sudo apt-get install python3-tk`).

### llama.cpp Server (Windows/NVIDIA)
- To run a local model server, download llama.cpp binaries and the CUDA runtime and extract them into the SAME folder, e.g. `C:\llama-server`:
  - CUDA runtime ZIP: https://github.com/ggml-org/llama.cpp/releases/download/b6585/cudart-llama-bin-win-cuda-12.4-x64.zip
  - llama.cpp server ZIP: https://github.com/ggml-org/llama.cpp/releases/download/b6585/llama-b6585-bin-win-cuda-12.4-x64.zip
- After extracting both into one folder, you should have `llama-server.exe` alongside the required CUDA DLLs.
- In the app, open the “Server Config” tab and point the executable path to that `llama-server.exe`, then configure flags and start the server.
- CPU‑only users can use a CPU build of llama.cpp or compile from source; update the path accordingly.

### Linux / macOS
- Note: the app has not been tested by the maintainer on Linux or macOS yet.
- You must download platform‑appropriate builds from the main llama.cpp releases page (the Windows ZIP links above will not work on non‑Windows):
  - https://github.com/ggml-org/llama.cpp/releases
- After downloading the correct package for your OS (e.g., Metal build for Apple silicon), ensure the `llama-server` binary and any required runtime libraries are in the same folder, then point the Server Config tab to that executable.

## Quick Start (Windows)
1. Download the ZIP from the repository page and extract.
2. Double‑click `run_app.bat`.
   - Creates `venv/` and installs dependencies (first time can take a few minutes).
   - Launches the app window.
3. Optional: If you plan to run a local model server, set it up in the “Server Config” tab.

## Quick Start (macOS/Linux)
- Use the helper script or run manually:
  ```bash
  bash run_app.sh  # creates .venv and installs deps
  # or manual steps
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python3 main.py
  ```

## Using The App
- Server Config
  - Select `llama-server` executable and configure flags (host/port, context size, GPU settings, API key if needed).
  - Start/stop the server; health checks and process cleanup are integrated.
- API Parameters
  - Parameters come from `config/openai_api_schema.json`.
  - Enable/tune values, preview the request JSON, send a quick chat/text call to the configured endpoint.
- Dataset Conversion
  - Click “Load Complete Dataset” to fetch core LiveBench categories (reasoning, math, coding, data_analysis, language, instruction_following).
  - Pick a category/subcategory, browse questions/ground truth, and export to text under `data/exported_datasets/`.
- Run Benchmark
  - Select an exported dataset and API/server configs; run benchmarks and record results.
- Scoring & Analysis
  - Explore completed runs and stats.
- Auto Mode
  - Automated parameter exploration based on curated parameter arrays and sampler sequences; writes a SQLite DB under `data/aco_runs/`.
- ACO Data Viewer
  - Open a run DB and inspect optimization progress and results.

## Endpoints
- Chat Completions: `POST /v1/chat/completions` (messages)
- Completions: `POST /v1/completions` (prompt)
- Health: `GET /health`, Slots: `GET /slots`
- Switch active endpoint type from the global bar at the top of the UI.

## Project Structure
```
config/                 # UI + schema for parameters and server flags
benchmarking/           # dataset loader/cache, runner, algorithms, ACO, scoring
managers/               # path, server config, parameter config, settings
ui/                     # Tkinter tabs and layout helpers
utils/                  # API client, server process mgmt, config helpers, logging
data/                   # user data (ignored in git except examples/.gitkeep)
  ├─ exported_datasets/ # text exports (created by Dataset Conversion)
  ├─ server_configs/    # saved server configs (examples tracked)
  ├─ saved_configs/     # saved API parameter configs (examples tracked)
  ├─ benchmarks/runs/   # per‑run outputs
  ├─ aco_runs/          # optimization SQLite databases
  ├─ cache/             # dataset metadata cache (rebuilt on demand)
```

## Dependencies
- Pinned for Python 3.11‑3.13 compatibility with LiveBench:
  - `datasets>=4,<5`
  - `huggingface_hub>=0.34,<1`
  - `pyarrow>=14,<19`
  - `requests>=2.31,<3`
- First run may download ~50–150 MB of wheels (numpy, pandas, pyarrow, etc.).

## Data & Privacy
- No API keys or secrets are stored in the repo.
- `data/` contains user‑generated content and caches. The repo tracks only examples and `.gitkeep` placeholders.
- The Dataset Conversion tab fetches public dataset metadata from Hugging Face.

## Troubleshooting
- “Missing Tk/Tkinter” (Linux/macOS): install Tk (`python3-tk`) and retry.
- “Install failures”: delete `venv/` (or `.venv/`) and re‑run the launcher to recreate the environment.
- Dataset issues:
  - Ensure internet access on first load.
  - Click “Load Complete Dataset” to force a fresh cache rebuild.
- Server connection errors: verify host/port/timeouts on the Server Config tab; confirm `llama-server` is running.

## Roadmap / Notes
- UI polish is ongoing; tabs are being converged on shared layout helpers.
- Auto Mode branch scheduler and additional sampler families are planned.
- Contributions/issues are welcome via GitHub.

## License
This project is released under the MIT License (see `LICENSE`).

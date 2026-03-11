# Lossless Context Management for Recursive Language Models (Hybrid LLM Agent Architecture)

## Overview

This project implements an enterprise-grade AI Agent system that combines a Lossless Context Management (LCM) architecture with Recursive Language Models (RLM). It is specifically engineered to operate smoothly on resource-constrained hardware, such as consumer GPUs with only 6GB of VRAM (e.g., RTX 4050), by optimizing memory utilization and employing intelligent execution routing.

When building highly autonomous AI Agents, the most significant challenges are the "Overflow Context Window" and Out-of-Memory (OOM) errors that occur when the model attempts to retain too much conversation history or execute overly complex recursive logic.

This repository solves these fundamental issues by separating the "thinking" process from the "memory management" process.

## Core Concepts

To grasp the power of this system, it is essential to understand the two core pillars it is built upon:

### 1. RLM (Recursive Language Models) - The Active Brain
Unlike traditional Large Language Models (LLMs) that simply receive a prompt and generate a single response passively, RLM transforms the LLM into an autonomous agent.
- **Principle:** The RLM operates within an execution environment (like a Python REPL sandbox). It reasons independently, generates code, executes that code, reads the resulting logs or errors, and recursively calls itself to correct mistakes or proceed to subsequent steps until the objective is achieved.
- **Vulnerability:** If an RLM operates without strict constraints, it is highly susceptible to falling into infinite loops, generating excessive "garbage" logs that flood the Context Window, and experiencing "hallucinations" where it forgets its original goal.

### 2. LCM (Lossless Context Management) - The Control Operating System
LCM was developed to mitigate the critical vulnerabilities of RLMs. Instead of forcing the LLM to remember everything and write its own error-prone recursive loops, LCM abstracts this responsibility to a deterministic Engine.
- **The Dual-State Memory Concept:**
  - **Immutable Store:** Every raw message, thought process, and execution log is permanently saved into a Database.
  - **Active Context:** Only the most recent messages and compressed "Summary Nodes" from the past are loaded into the VRAM at any given time, guaranteeing that the memory limit is never breached.
- **Directed Acyclic Graph (DAG) Structure:** LCM compresses outdated conversation turns into summary nodes while retaining lineage pointers back to the original raw data. This structure ensures that the Agent can "losslessly" recall any specific granular detail from the past when necessary.

**The Hybrid Approach:** The RLM acts as the "Scientist" who continuously thinks and experiments, while the LCM acts as the "Lab Manager" who cleans up the workspace, organizes documents, and manages parallel worker threads so the Scientist is never overwhelmed.

## System Architecture and Execution Strategy

Due to the strict 6GB VRAM limitation, the system employs aggressive offloading and flexible Model Routing strategies, intentionally avoiding heavy backends.

### 1. Infrastructure and Backends
- **Inference Backend:** The system utilizes Ollama as the core model execution engine. Ollama is highly optimized for GGUF formats, automatically manages the KV Cache, swaps models rapidly, and features a fallback mechanism to System RAM, preventing hard OOM crashes.
- **Database (Immutable Store):** The system relies on PostgreSQL (or SQLite for development) to store the LCM's Directed Acyclic Graph, including raw messages, summaries, and metadata.

### 2. Model Routing Strategy
- **The Main Brain (RLM):** Responsible for high-level planning and decision making. (Recommended: `qwen2.5-coder:3b` or `qwen3.5:4b` to ensure strong coding capabilities and format adherence).
- **The Sub-Agent Squad (LCM Workers):** Used for parallel processing and multi-threading.
  - **Model:** A highly lightweight model (Recommended: `qwen2.5-coder:0.5b` or `qwen3.5:0.8b`). These models respond in milliseconds and are perfect for a worker pool executing compartmentalized tasks.

## Advanced Mechanisms and Operators

The RLM Brain orchestrates tasks through the LCM's suite of operators, combined with state-of-the-art prompting techniques.

### 1. Operator-Level Recursion
These functions transfer the responsibility of parallel execution and retry logic from the LLM to the deterministic system engine.

- **Skeleton-of-Thought (SoT) + `llm_map`:**
  - **Mechanism:** The main RLM uses SoT to outline task steps, then delegates raw processing to `llm_map`.
  - **`llm_map`:** Processes items in parallel by spawning independent LLM API calls. The engine manages a worker pool (e.g., 16 lightweight workers running concurrently), validates responses against JSON Schemas, and handles retries automatically. Ideal for high-throughput, side-effect-free tasks like classification or entity extraction.

- **ReAct + `agentic_map`:**
  - **Mechanism:** When a task requires high adaptability, the RLM invokes `agentic_map` to spawn Sub-Agents.
  - **Execution:** Creates a fully functional session for each data item. Sub-Agents utilize a ReAct (Reasoning and Acting) loop for multi-step inference, leveraging tools like file readers, web search, or REPL execution.

### 2. Direction and Moderation (Pre/Post Processing)
- **Directional Stimulus Prompting (DSP):** Before pushing data into parallel processing, DSP generates "directional keywords" attached to the operators. This guides the lightweight 0.5b models, significantly reducing hallucinations.
- **DSPy Compilation:** Utilized to automatically optimize LCM summary prompts, ensuring high-quality DAG nodes that do not drop critical information over long conversations.
- **Reflexion / LogiCoT (Self-Evaluation):** Integrated into the LCM's escalation protocol. The LLM self-evaluates its summary or Sub-Agent output before the Engine commits it to the Immutable Store.

### 3. Context Retrieval and Expansion
These functions interact directly with the LCM DAG to retrieve compressed information, supporting Tree of Thoughts (ToT) or Graph of Thoughts (GoT) reasoning when backtracking is required.

- **`lcm_describe`:** Displays metadata about the origin of a summary (type, context state, destination). The agent uses this to check lineage and select the correct node to traverse.
- **`lcm_expand`:** Guarantees "lossless" memory. It follows lineage pointers to restore a summary back to its exact original, uncompressed raw text.
- **`lcm_read`:** Large files are replaced with reference tags (e.g., `file_001`) in the Active Context. Sub-Agents use `lcm_read` to paginate through the data block by block.
- **`lcm_grep`:** Performs direct regex searches across the entire raw database history, bypassing the Active Context limitation entirely.

## Practical Execution Workflow Example

**Scenario:** Analyze and fix an Out of Memory (OOM) systemic error from a directory containing 5 massive system log files.

1. **Context Bypass:** LCM automatically stores the 5 log files outside the active context, giving the RLM only 5 ID references (`file_001` to `file_005`) and 5 brief Exploration Summaries.
2. **Planning (SoT):** The 3B RLM reads the summaries and outlines an investigation plan.
3. **Direction (DSP) & Parallelization (`llm_map`):** The RLM attaches keywords (e.g., "Memory limit exceeded", "Crash stack"), and calls `llm_map` to spawn 16 lightweight workers (0.5B). These workers use `lcm_read` in parallel to scan chunks of the 5 logs.
4. **Moderation (Reflexion):** The engine aggregates the results. A dedicated Sub-Agent reviews the findings to filter out false positives.
5. **Reasoning & Actions (`agentic_map`):** The RLM receives the cleaned data, identifies the faulty function, and uses `agentic_map` to spawn a sandboxed Sub-Agent. This agent runs a ReAct loop to write a patch and test the fix.
6. **Immutable Storage (DAG):** Throughout this process, every thought, tool call, and result is compressed by the Engine into DAG nodes in the database. The RLM can always call `lcm_expand` to retrieve the exact stack trace if it needs to attempt a different solution path.

## System Prerequisites

To run this project locally, ensure your environment meets the following specifications:

- **Operating System:** Windows, Linux, or macOS.
- **Python:** Version 3.10 or higher.
- **Inference Engine:** Ollama must be installed and running as the local LLM host.
- **Hardware:** Minimum of 6GB VRAM (Optimized for entry-level modern GPUs like RTX 4050 or equivalent).

## Installation Guide

Follow these steps to set up the project on your local machine:

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/HoangQuangMinh23BI14281/Lossless-Context-Management-for-Recursive-Language-Models.git
   cd Lossless-Context-Management-for-Recursive-Language-Models
   ```

2. **Set up a Virtual Environment:**
   It is highly recommended to use an isolated Python environment.
   ```bash
   python -m venv venv
   
   # For Windows users:
   .\venv\Scripts\activate
   
   # For Linux/macOS users:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   Install the required Python packages defined in the requirements file.
   ```bash
   pip install -r requirements.txt
   ```

## Configuration and Environment Variables

The system relies on a `.env` file to manage environment parameters securely. You must create this file before running the application.

1. **Copy the example configuration:**
   ```bash
   cp .env-example .env
   ```

2. **Configure your parameters:**
   Open the `.env` file and adjust the settings according to your hardware and preferences. Below are the key variables:

   - `OLLAMA_BASE_URL`: The API endpoint for your Ollama instance (Default: `http://localhost:11434`).
   - `RLM_MODEL`: The primary model used for the "Brain" reasoning tasks (Default: `qwen3.5:4b` or `qwen2.5-coder:3b`).
   - `LCM_WORKER_MODEL`: The highly efficient model used for parallel background workers (Default: `qwen3.5:0.8b` or `qwen2.5-coder:0.5b`).
   - `DATABASE_URL`: The connection string for the Immutable Store. SQLite is used as default for rapid prototyping (`sqlite+aiosqlite:///lcm_store.db`).
   - `MAX_WORKERS`: The maximum number of parallel threads/Sub-Agents allowed (Default: 16). Adjust based on system RAM and CPU.
   - `VRAM_LIMIT_GB`: The hard limit for VRAM utilization (Default: 6).

## Usage Scenarios

The project supports three distinct operational modes, catering to different development and deployment needs. These are triggered via command-line arguments to `main.py`.

### 1. Interactive Command Line Interface (CLI REPL)
This is the default mode, providing a direct, interactive terminal session with the Hybrid RLM Agent.

```bash
python main.py
```

**Supported Commands within REPL:**
- `dashboard`: Generates and opens an HTML report visualizing the current LCM DAG structure and memory usage.
- `status`: Prints a quick summary of active tokens and resource utilization.
- `file:path/to/your/file.txt`: Directly loads the content of a local file into the active context or creates a reference node for large files.
- `exit` or `quit`: Safely terminates the session and shuts down the engine.

### 2. Web User Interface (Premium UI)
Launches a FastAPI backend served alongside a modern, intuitive web dashboard for a visual interaction experience.

```bash
python main.py --ui
```
*Once initialized, the application will automatically open `http://localhost:8000` in your default web browser.*

### 3. Model Context Protocol (MCP Server)
Initiates the application as a standalone MCP server. This allows the sophisticated Agentic engine to be integrated directly into other AI toolchains, modern IDEs (like Cursor), or external multi-agent frameworks.

```bash
python main.py --mcp
```

## Project Directory Structure

Understanding the repository layout will help in navigating the codebase:

- `core/`: Contains the foundational logic and base classes for the application.
- `database/`: Modules handling connections, ORM definitions, and the DAG logic for SQLite or PostgreSQL.
- `exploration/`: Toolsets designed for scanning, filtering, and searching through massive datasets or file systems without loading them into memory.
- `frontend/`: Static assets (HTML, CSS, JS) utilized when running the `--ui` mode.
- `logger/`: A comprehensive, multi-tiered logging system bridging the gap between raw execution logs and the REPL interface.
- `operators/`: The robust set of recursive mathematical and logical operators (Skeleton-of-Thought, ReAct, `llm_map`, `agentic_map`).
- `prompts/`: System prompts, DSP templates, and Reflexion evaluation criteria.
- `retrieval/`: The LCM specific controllers (`lcm_read`, `lcm_expand`, `lcm_describe`).
- `rlm/`: The core RLM Brain module, semantic parser, and the isolated execution sandbox for safe code evaluation.
- `schemas/`: Pydantic data models enforcing strict typing for the DAG nodes and tool inputs/outputs.
- `tools/`: Extensible toolsets available for the ReAct agents, including file system manipulators and a Bash execution environment.
- `runs/`: A generated directory containing execution artifacts, HTML graphs, and session dashboards.

## License and Contribution

*This project is currently under active research and development.*
Feel free to open issues or submit pull requests if you encounter bugs or have suggestions for optimization, specifically regarding memory management on lower-end hardware.
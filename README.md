# Open WebUI Verilog Tools - User Guide

Complete guide for using Open WebUI with vLLM and custom Verilog development tools in local server.

## 1. Activate Conda Environment

```bash
conda activate open-webui
```

## 2. Start vLLM Server

Host DeepSeek-Coder-6.7B model:

```bash
vllm serve deepseek-ai/deepseek-coder-6.7b-instruct \
    --max-model-len 32768 \
    --port 8000
```

**Key Parameters:**

- `--max-model-len 32768`: Context window size
- `--port 8000`: API endpoint at `http://localhost:8000`

## 3. Start Open WebUI

**Command:**

```bash
open-webui serve
```

Access at: **[http://localhost:8080](http://localhost:8080)**

**Default Admin Credentials:**

- Email: `admin1@example.com`
- Password: `123456789`

## Project Structure

```text
vLLM_OpenWebUI/
├── src/
│   └── function/               # Custom Open WebUI functions
│       ├── openwebui_verilator_action.py  # Verilog Syntax Checker (Action)
│       ├── openwebui_verilator_pipe.py    # Verilog Syntax Auto-Fix (Pipe)
│       ├── openwebui_testbench_action.py  # Testbench Generator (Action)
│       └── openwebui_schematic_action.py  # Schematic Viewer (Action)
├── README.md                      # This file
└── ...
```

## Admin Panel Configuration

### Uploading Custom Functions

To use the custom Verilog tools, you need to upload them through Open WebUI's admin panel:

1. **Access Admin Panel**
   - Navigate to **Settings** → **Admin Panel** → **Functions**

2. **Add New Function**
   - Click the **"+"** button to create a new function
   - Copy the content from one of the Python files in `src/function/`
   - Paste it into the function editor

3. **Enable the Function**
   - Toggle the function to **enabled** state
   - Configure any custom settings in the "Valves" section (paths, timeouts, etc.)
   - Click **Save**

4. **Verify Installation**
   - Start a new chat with your model
   - Look for action buttons (e.g., "Check Verilog Syntax") below the message input
   - The buttons appear after the assistant generates Verilog code

### Example: Configuring Verilator Action

After uploading `openwebui_verilator_action.py`, configure these valves:

- **verilator_path**: Path to verilator executable (default: `verilator`)
- **temp_dir**: Directory for temporary files (default: `/home/nntkim/Chatbox/pyverilator/temp`)

**Note:** Update the `temp_dir` path to match your system's directory structure.

![Open WebUI Functions Panel](https://github.com/EtiennePerot/safe-code-execution/blob/master/res/functions.png?raw=true)

## Custom Tools

This project includes four custom Open WebUI functions (Actions and Pipes) for Verilog development:

### 1. Verilog Syntax Auto-Fix (Pipe)

**File:** `src/function/openwebui_verilator_pipe.py`

An intelligent "Pipe" function that automatically monitors conversation flow. If it detects Verilog code with syntax errors, it transparently prompts the LLM to fix the code until it passes Verilator verification.

**Features:**
- **Automatic & Proactive**: Works in the background without requiring user clicks.
- **Self-Healing**: Automatically triggers regeneration loop if errors are found.
- **Verified Output**: Ensures the code shown in chat is syntactically correct.
- **Configurable Retries**: Set maximum regeneration attempts (default: 3).
- **Context Management**: Handles token limits during repair loops.

**Usage**: Enable this function in the Admin Panel. It will automatically intercept and verify Verilog code blocks.

---

### 2. Verilog Syntax Checker (Action)

**File:** `src/function/openwebui_verilator_action.py`

Manual action button to validate Verilog code syntax using Verilator's lint-only mode.

**Features:**
- Extracts Verilog code blocks from assistant messages.
- Checks syntax for all detected modules.
- Color-coded results (🟢 OK, 🟡 Warnings, 🔴 Errors).
- Filters out verbose Verilator informational output.

**Usage:** Click the "Check Verilog Syntax" action button below a message containing Verilog code.

---

### 3. Testbench Generator & Simulator (Action)

**File:** `src/function/openwebui_testbench_action.py`

Generates testbenches using the LLM and runs simulations with Icarus Verilog.

**Features:**
- Extracts Verilog modules and analyzes ports.
- Uses DeepSeek model to generate comprehensive testbenches.
- Compiles and simulates using Icarus Verilog (iverilog + vvp).
- Displays waveform generation commands and simulation logs.

**Usage:** Click the "Generate & Run Testbench" action button after receiving Verilog design code.

---

### 4. Schematic Viewer (Action)

**File:** `src/function/openwebui_schematic_action.py`

Generates visual gate-level schematics from Verilog code using Yosys.

**Features:**
- Synthesizes Verilog to gate-level netlist.
- Generates SVG schematic diagrams using `netlistsvg` or Yosys internal tools.
- Displays schematics inline in the chat interface.

**Usage:** Click the "Schematic Viewer (Yosys)" action button to visualize Verilog module structure.

## Resources

### Open WebUI Functions Documentation

For detailed information on creating and using custom functions in Open WebUI:

**[Open WebUI Functions Guide](https://docs.openwebui.com/features/plugin/functions/)**

This documentation covers:

- Function structure and syntax
- How to upload and manage functions
- Event hooks and integration patterns
- Best practices for custom tool development

### Safe Code Execution for Open WebUI

**Reference:** [Safe Code Execution by EtiennePerot](https://github.com/EtiennePerot/safe-code-execution)

This project's Verilog tools are inspired by the safe code execution pattern used in Open WebUI. The concept enables LLMs to execute code securely through sandboxed environments.

## Notes

- Ensure vLLM server is running before starting Open WebUI
- The model will be available at the OpenAI-compatible endpoint
- Custom functions must be uploaded through Open WebUI's admin panel

## Future Development

For planned features based on research papers (COMBA-PROMPT & REFINE-Verilog), see:

**[README_FutureWork.md](README_FutureWork.md)**

[fuction](res/functions.png)

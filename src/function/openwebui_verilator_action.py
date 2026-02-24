"""
title: Check Verilog Syntax
author: user
version: 1.0.0
type: action
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIwIDYgOSAxNyA0IDEyIj48L3BvbHlsaW5lPjwvc3ZnPg==
"""

import subprocess
import os
import re
from typing import Optional, List
from pydantic import BaseModel, Field


class Action:
    class Valves(BaseModel):
        verilator_path: str = Field(
            default="verilator",
            description="Path to verilator executable"
        )
        temp_dir: str = Field(
            default="/home/nntkim/Chatbox/pyverilator/temp",
            description="Directory to save temporary Verilog files"
        )

    def __init__(self):
        self.valves = self.Valves()
        os.makedirs(self.valves.temp_dir, exist_ok=True)

    async def action(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
        __event_call__=None,
    ) -> Optional[dict]:
        """
        Action button to check Verilog syntax in the last assistant message.
        """
        # Show waiting status immediately
        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "⏳ Waiting... Checking syntax", "done": False},
            }
        )
        
        messages = body.get("messages", [])
        if not messages:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "No messages found", "done": True},
                }
            )
            return None

        # Find the last assistant message
        assistant_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                assistant_msg = msg
                break

        if not assistant_msg:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "No assistant message found", "done": True},
                }
            )
            return None

        content = assistant_msg.get("content", "")
        
        # Extract Verilog code blocks
        code_blocks = self._extract_verilog_blocks(content)
        
        if not code_blocks:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "No Verilog code found in response", "done": True},
                }
            )
            return None

        # Check each code block
        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": f"Checking {len(code_blocks)} Verilog block(s)...", "done": False},
            }
        )

        results = []
        for i, code in enumerate(code_blocks):
            module_name = self._extract_module_name(code) or f"block_{i+1}"
            result = self._check_code_syntax(code, module_name)
            results.append(result)

        # Emit results as a message
        results_text = "\n\n".join(results)
        await __event_emitter__(
            {
                "type": "message",
                "data": {"content": f"\n\n---\n\n**🔍 SYNTAX CHECK RESULTS:**\n\n{results_text}"},
            }
        )

        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "Syntax check complete", "done": True},
            }
        )

        return None

    def _extract_verilog_blocks(self, text: str) -> List[str]:
        """Extract all Verilog code blocks from markdown."""
        patterns = [
            r"```(?:verilog|v|systemverilog|sv)\n(.*?)```",
            r"```\n(module\s+\w+.*?)```",
        ]
        
        blocks = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            blocks.extend(matches)
        
        return [b.strip() for b in blocks if b.strip() and "module" in b.lower()]

    def _extract_module_name(self, code: str) -> Optional[str]:
        """Extract module name from Verilog code."""
        match = re.search(r'module\s+(\w+)', code, re.IGNORECASE)
        return match.group(1) if match else None

    def _check_code_syntax(self, code: str, module_name: str) -> str:
        """Check syntax of Verilog code string."""
        file_path = os.path.join(self.valves.temp_dir, f"{module_name}.v")
        
        try:
            with open(file_path, "w") as f:
                f.write(code)
        except Exception as e:
            return f"🔴 **{module_name}**: Failed to save - {str(e)}"

        return self._run_verilator(file_path, module_name)

    def _run_verilator(self, file_path: str, display_name: str) -> str:
        """Run verilator and return formatted result."""
        cmd = [self.valves.verilator_path, "--lint-only", file_path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = (result.stderr + result.stdout).strip()
            
            # Filter out informational Verilation Report
            filtered_lines = []
            for line in output.split('\n'):
                # Check for spaced-out "V e r i l a t i o n" or normal patterns
                line_no_spaces = line.replace(' ', '')
                if any(skip in line_no_spaces for skip in [
                    'VerilationReport',
                    'Verilator:',
                    '-Verilator',
                ]):
                    continue
                if line.strip():
                    filtered_lines.append(line)
            
            filtered_output = '\n'.join(filtered_lines).strip()

            if result.returncode == 0 and not filtered_output:
                return f"🟢 **{display_name}**: Syntax OK ✓"
            elif result.returncode == 0:
                return f"🟡 **{display_name}**: Passed with warnings\n```\n{filtered_output}\n```"
            else:
                return f"🔴 **{display_name}**: Syntax errors\n```\n{filtered_output}\n```"

        except subprocess.TimeoutExpired:
            return f"🔴 **{display_name}**: Verilator timeout"
        except FileNotFoundError:
            return f"🔴 **{display_name}**: Verilator not found"

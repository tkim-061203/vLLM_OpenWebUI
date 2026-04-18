"""
title: Report Logic Gates (Yosys)
author: user
version: 1.0.0
type: action
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xNCAxMlY2YTIgMiAwIDAgMC0yLTJINHYxNmg4YTIgMiAwIDAgMCAyLTJ2LTZaIi8+PHBhdGggZD0iTTIgOWgyIi8+PHBhdGggZD0iTTIgMTVoMiIvPjxwYXRoIGQ9Ik0xNCAxMmg4Ii8+PC9zdmc+
"""

import subprocess
import os
import re
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class Action:
    class Valves(BaseModel):
        yosys_path: str = Field(
            default="yosys",
            description="Path to yosys executable"
        )
        temp_dir: str = Field(
            default="/home/nntkim/vLLM_OpenWebUI/temp",
            description="Directory for temporary files"
        )
        timeout: int = Field(
            default=60,
            description="Yosys timeout in seconds"
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
        Action button to report logic gate statistics using Yosys.
        """
        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "⏳ Analyzing logic gates...", "done": False},
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

        # Find the last assistant message with Verilog code
        verilog_code = None
        module_name = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                codes = self._extract_verilog_blocks(content)
                if codes:
                    for code in codes:
                        m_name = self._extract_module_name(code)
                        if m_name and not (m_name.lower().startswith("tb_") or m_name.lower().startswith("test_")):
                            verilog_code = code
                            module_name = m_name
                            break
                    if verilog_code:
                        break

        if not verilog_code or not module_name:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "No Verilog module found", "done": True},
                }
            )
            return None

        # Save Verilog to temp file
        verilog_file = os.path.join(self.valves.temp_dir, f"{module_name}_gate_report.v")
        try:
            with open(verilog_file, "w") as f:
                f.write(verilog_code)
        except Exception as e:
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n---\n\n❌ Failed to save file: {e}"},
                }
            )
            return None

        # Run Yosys stat
        result_text = self._run_yosys_stat(verilog_file, module_name)
        
        await __event_emitter__(
            {
                "type": "message",
                "data": {"content": f"\n\n---\n\n**📊 LOGIC GATE REPORT: `{module_name}`**\n\n{result_text}"},
            }
        )

        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "Analysis complete", "done": True},
            }
        )

        return None

    def _extract_verilog_blocks(self, text: str) -> List[str]:
        """Extract Verilog code blocks from markdown."""
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

    def _run_yosys_stat(self, verilog_file: str, module_name: str) -> str:
        """Run Yosys to get statistics."""
        yosys_script = f"""
                        read_verilog {verilog_file}
                        hierarchy -check -top {module_name}
                        synth
                        stat
                        """
        
        script_file = os.path.join(self.valves.temp_dir, f"{module_name}_stat.ys")
        with open(script_file, "w") as f:
            f.write(yosys_script)
        
        try:
            result = subprocess.run(
                [self.valves.yosys_path, "-s", script_file],
                capture_output=True,
                text=True,
                timeout=self.valves.timeout,
                cwd=self.valves.temp_dir
            )
            
            if result.returncode != 0:
                stderr = result.stderr.strip()
                return f"❌ **Yosys Error:**\n```\n{stderr}\n```"
            
            return self._parse_stat_output(result.stdout, module_name)
            
        except subprocess.TimeoutExpired:
            return f"❌ Yosys timed out after {self.valves.timeout}s"
        except FileNotFoundError:
            return "❌ Yosys not found. Is it installed and in PATH?"

    def _parse_stat_output(self, output: str, top_module: str) -> str:
        """Parse Yosys stat output into a clean markdown report."""
        # Find the section for the top module
        # It looks like: === module_name ===
        module_pattern = rf"=== {top_module} ==="
        if module_pattern not in output:
            # If explicit module name not found, try to find the last statistics block
            blocks = re.split(r"=== \w+ ===", output)
            if len(blocks) > 1:
                stats_block = blocks[-1]
            else:
                stats_block = output
        else:
            stats_block = output.split(module_pattern)[-1].split("===")[0]

        # Extract stats
        lines = stats_block.strip().split('\n')
        
        general_stats = {}
        cell_stats = []
        
        in_cells = False
        
        for line in lines:
            line = line.strip()
            if not line or '|' in line or '+' in line: continue
            
            # Handle both "Number of cells: 5" and "5 cells" formats
            if 'cells' in line.lower() and not in_cells:
                in_cells = True
                match = re.search(r'(\d+)\s+cells|Number of cells:\s+(\d+)', line)
                if match:
                    count = match.group(1) or match.group(2)
                    general_stats['Total Cells'] = count
                continue
                
            if not in_cells:
                # General stats: wires, bits, etc.
                # Style 1: "Number of wires: 8"
                # Style 2: "8 wires"
                match = re.search(r'Number of ([\w\s]+):\s+(\d+)|(\d+)\s+([\w\s]+)', line)
                if match:
                    if match.group(1): # Style 1
                        key, val = match.group(1).title(), match.group(2)
                    else: # Style 2
                        key, val = match.group(4).title(), match.group(3)
                    general_stats[key] = val
            else:
                # We are in cell list
                # Format: gate_name  count or count gate_name
                # Style 1: "$_AND_  1"
                # Style 2: "1  $_AND_"
                match = re.search(r'^\s*([\$A-Za-z0-9_]+)\s+(\d+)\s*$|^\s*(\d+)\s+([\$A-Za-z0-9_]+)\s*$', line)
                if match:
                    if match.group(1):
                        cell_stats.append((match.group(1), match.group(2)))
                    else:
                        cell_stats.append((match.group(4), match.group(3)))

        # Build Markdown Table
        report = "### Summary\n\n"
        if not general_stats and not cell_stats:
            return "⚠️ Could not parse Yosys statistics. Please check the raw output if available."

        report += "| Metric | Count |\n"
        report += "| :--- | :--- |\n"
        for k, v in general_stats.items():
            report += f"| {k} | {v} |\n"
            
        if cell_stats:
            report += "\n### Cell Breakdown (Logic Gates)\n\n"
            report += "| Gate Type | Count |\n"
            report += "| :--- | :--- |\n"
            for gate, count in cell_stats:
                # Clean up gate name (remove $_ prefix)
                display_gate = gate.replace('$_', '').replace('_', '')
                report += f"| `{display_gate}` | {count} |\n"
        
        return report

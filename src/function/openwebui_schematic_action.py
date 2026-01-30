"""
title: Schematic Viewer (Yosys)
author: user
version: 2.0.0
type: action
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxyZWN0IHg9IjMiIHk9IjMiIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgcng9IjIiLz48cGF0aCBkPSJNMyA5aDEiLz48cGF0aCBkPSJNMyAxNWgxIi8+PHBhdGggZD0iTTIwIDloMSIvPjxwYXRoIGQ9Ik0yMCAxNWgxIi8+PC9zdmc+
"""

import subprocess
import os
import re
import base64
from typing import Optional, List
from pydantic import BaseModel, Field


class Action:
    class Valves(BaseModel):
        yosys_path: str = Field(
            default="yosys",
            description="Path to yosys executable"
        )
        temp_dir: str = Field(
            default="/home/nntkim/Chatbox/pyverilator/temp",
            description="Directory for temporary files"
        )
        timeout: int = Field(
            default=60,
            description="Yosys timeout in seconds"
        )
        use_netlistsvg: bool = Field(
            default=False,
            description="Use netlistsvg for SVG generation (requires npm package)"
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
        Action button to generate schematic using Yosys.
        """
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
                    verilog_code = codes[0]
                    module_name = self._extract_module_name(verilog_code)
                    break

        if not verilog_code or not module_name:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "No Verilog module found", "done": True},
                }
            )
            return None

        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": f"Generating schematic for {module_name}...", "done": False},
            }
        )

        # Save Verilog to temp file
        verilog_file = os.path.join(self.valves.temp_dir, f"{module_name}.v")
        svg_prefix = os.path.join(self.valves.temp_dir, module_name)
        
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

        # Generate schematic using Yosys
        result = self._run_yosys(verilog_file, svg_prefix, module_name)
        
        if result.startswith("❌"):
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n---\n\n**📐 SCHEMATIC GENERATION:**\n\n{result}"},
                }
            )
        else:
            # Yosys creates .dot.svg file, try both possible names
            svg_files = [
                f"{svg_prefix}.dot.svg",
                f"{svg_prefix}.svg"
            ]
            
            svg_content = None
            for svg_file in svg_files:
                if os.path.exists(svg_file):
                    try:
                        with open(svg_file, "r") as f:
                            svg_content = f.read()
                        break
                    except Exception as e:
                        continue
            
            if svg_content:
                # Convert SVG to base64 for proper image display
                svg_b64 = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
                svg_data_uri = f"data:image/svg+xml;base64,{svg_b64}"
                
                result_text = f"""
---

**📐 SCHEMATIC VIEW: `{module_name}`**

![Schematic]({svg_data_uri})

{result}
"""
                await __event_emitter__(
                    {
                        "type": "message", 
                        "data": {"content": result_text},
                    }
                )
            else:
                # SVG file not found
                checked_files = "\n".join([f"- {f}" for f in svg_files])
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": f"\n\n---\n\n⚠️ SVG file not found.\n\n**Checked:**\n{checked_files}\n\n{result}"},
                    }
                )

        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "Schematic complete", "done": True},
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

    def _run_yosys(self, verilog_file: str, svg_file: str, module_name: str) -> str:
        """Run Yosys to generate schematic SVG."""
        
        # Yosys script to generate SVG
        # Using 'show' command with -format svg
        yosys_script = f"""
                        read_verilog {verilog_file}
                        hierarchy -check -top {module_name}
                        proc
                        opt
                        show -format svg -prefix {svg_file.replace('.svg', '')}
                        """
        
        script_file = os.path.join(self.valves.temp_dir, f"{module_name}_show.ys")
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
                # Check for common errors
                stderr = result.stderr.strip()
                if "ERROR" in stderr:
                    return f"❌ **Yosys Error:**\n```\n{stderr}\n```"
                return f"❌ **Yosys failed:**\n```\n{stderr}\n```"
            
            # Success - provide stats
            output = result.stdout
            
            # Parse some stats from yosys output
            stats = []
            for line in output.split('\n'):
                if 'Number of cells:' in line or \
                   'Number of wires:' in line or \
                   'Number of modules:' in line:
                    stats.append(line.strip())
            
            stats_text = "\n".join(stats) if stats else "Synthesis completed"
            return f"✅ **Generated with Yosys**\n\n```\n{stats_text}\n```"
            
        except subprocess.TimeoutExpired:
            return f"❌ Yosys timed out after {self.valves.timeout}s"
        except FileNotFoundError:
            return "❌ Yosys not found. Is it installed and in PATH?"

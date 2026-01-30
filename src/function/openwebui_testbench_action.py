"""
title: Generate & Run Testbench
author: user
version: 1.0.0
type: action
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5Z29uIHBvaW50cz0iNSAzIDEzIDEzIDIwIDEzIDEyIDIxIDQgMjEgMTIgMTMgNSAzIi8+PC9zdmc+
"""

import subprocess
import os
import re
import httpx
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field


class Action:
    class Valves(BaseModel):
        iverilog_path: str = Field(
            default="iverilog",
            description="Path to iverilog executable"
        )
        vvp_path: str = Field(
            default="vvp",
            description="Path to vvp simulator executable"
        )
        temp_dir: str = Field(
            default="/home/nntkim/Chatbox/pyverilator/temp",
            description="Directory to save temporary Verilog files"
        )
        timeout: int = Field(
            default=120,
            description="Simulation timeout in seconds"
        )
        openai_api_base: str = Field(
            default="http://localhost:8000/v1",
            description="OpenAI-compatible API base URL for LLM"
        )
        model_name: str = Field(
            default="deepseek-ai/deepseek-coder-6.7b-instruct",
            description="Model name for testbench generation"
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
        Action button to generate testbench and run simulation for the last Verilog code.
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
                    "data": {"description": "No Verilog module found in response", "done": True},
                }
            )
            return None

        # Step 1: Generate testbench
        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": f"Generating testbench for {module_name}...", "done": False},
            }
        )

        testbench_code = await self._generate_testbench(verilog_code, module_name)
        
        if testbench_code.startswith("❌"):
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n---\n\n**🧪 TESTBENCH GENERATION FAILED:**\n\n{testbench_code}"},
                }
            )
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Failed to generate testbench", "done": True},
                }
            )
            return None

        # Step 2: Save files and run simulation
        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "Running simulation...", "done": False},
            }
        )

        design_file = os.path.join(self.valves.temp_dir, f"{module_name}.v")
        tb_file = os.path.join(self.valves.temp_dir, f"tb_{module_name}.v")

        try:
            with open(design_file, "w") as f:
                f.write(verilog_code)
            with open(tb_file, "w") as f:
                f.write(testbench_code)
        except Exception as e:
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n---\n\n❌ Failed to save files: {e}"},
                }
            )
            return None

        # Step 3: Compile and run
        sim_result = self._run_simulation(design_file, tb_file, module_name)

        # Emit results
        result_text = f"""
---

**🧪 AUTO-GENERATED TESTBENCH:**

```verilog
{testbench_code}
```

**📊 SIMULATION RESULT:**

{sim_result}
"""
        await __event_emitter__(
            {
                "type": "message",
                "data": {"content": result_text},
            }
        )

        await __event_emitter__(
            {
                "type": "status",
                "data": {"description": "Testbench complete", "done": True},
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

    def _extract_ports(self, code: str) -> Tuple[List[str], List[str]]:
        """Extract input and output port names from Verilog code."""
        inputs = re.findall(r'input\s+(?:wire|reg)?\s*(?:\[[^\]]+\])?\s*(\w+)', code, re.IGNORECASE)
        outputs = re.findall(r'output\s+(?:wire|reg)?\s*(?:\[[^\]]+\])?\s*(\w+)', code, re.IGNORECASE)
        return inputs, outputs

    async def _generate_testbench(self, verilog_code: str, module_name: str) -> str:
        """Generate testbench using the LLM."""
        prompt = f"""Generate a simple Verilog testbench for the following module.
The testbench should:
1. Instantiate the module
2. Apply test vectors to all inputs
3. Print "TEST PASSED" if outputs are correct, "TEST FAILED" otherwise
4. Use $display for output messages
5. End with $finish

Module code:
```verilog
{verilog_code}
```

Generate ONLY the testbench code, no explanations. The testbench module should be named tb_{module_name}."""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.valves.openai_api_base}/chat/completions",
                    json={
                        "model": self.valves.model_name,
                        "messages": [
                            {"role": "system", "content": "You are a Verilog expert. Generate only code, no explanations."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2048
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    return f"❌ LLM API error: {response.status_code}"
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # Extract code block from response
                codes = self._extract_verilog_blocks(content)
                if codes:
                    return codes[0]
                
                # If no code block, try to use raw content if it looks like Verilog
                if "module" in content.lower() and "endmodule" in content.lower():
                    # Clean up the content
                    lines = content.split('\n')
                    code_lines = []
                    in_code = False
                    for line in lines:
                        if 'module' in line.lower() or in_code:
                            in_code = True
                            code_lines.append(line)
                            if 'endmodule' in line.lower():
                                break
                    if code_lines:
                        return '\n'.join(code_lines)
                
                return f"❌ Could not extract testbench from LLM response"
                
        except httpx.TimeoutException:
            return "❌ LLM request timed out"
        except Exception as e:
            return f"❌ LLM error: {str(e)}"

    def _run_simulation(self, design_file: str, tb_file: str, module_name: str) -> str:
        """Compile and run simulation using Icarus Verilog."""
        out_file = os.path.join(self.valves.temp_dir, f"{module_name}_sim.vvp")
        
        # Compile with iverilog
        cmd = [self.valves.iverilog_path, "-o", out_file, design_file, tb_file]
        
        try:
            compile_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if compile_result.returncode != 0:
                return f"❌ **Compilation failed:**\n```\n{compile_result.stderr}\n```"
            
            # Run simulation with vvp
            sim_result = subprocess.run(
                [self.valves.vvp_path, out_file],
                capture_output=True,
                text=True,
                timeout=self.valves.timeout
            )
            
            output = sim_result.stdout.strip()
            errors = sim_result.stderr.strip()
            
            # Analyze results
            output_upper = output.upper()
            if "PASS" in output_upper or "SUCCESS" in output_upper:
                status = "✅ **SIMULATION PASSED**"
            elif "FAIL" in output_upper or "ERROR" in output_upper:
                status = "❌ **SIMULATION FAILED**"
            else:
                status = "⚠️ **Simulation completed**"
            
            result = f"{status}\n\n```\n{output}\n```"
            if errors:
                result += f"\n\n**Warnings:**\n```\n{errors}\n```"
            
            return result
            
        except subprocess.TimeoutExpired:
            return f"❌ Simulation timed out after {self.valves.timeout}s"
        except FileNotFoundError as e:
            return f"❌ Tool not found: {e.filename}"



"""
title: Verilog Syntax Auto-Fix Pipe
author: user
version: 1.1.0
type: pipe
description: Automatically checks Verilog syntax and regenerates code if errors found
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIwIDYgOSAxNyA0IDEyIj48L3BvbHlsaW5lPjwvc3ZnPg==
"""

import subprocess
import os
import re
import requests
from typing import Optional, List, Generator, Iterator, Union
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        verilator_path: str = Field(
            default="verilator",
            description="Path to verilator executable"
        )
        temp_dir: str = Field(
            default="/home/nntkim/Chatbox/pyverilator/temp",
            description="Directory to save temporary Verilog files"
        )
        llm_api_url: str = Field(
            default="http://localhost:8000/v1/chat/completions",
            description="vLLM API endpoint URL"
        )
        model_name: str = Field(
            default="deepseek-ai/deepseek-coder-6.7b-instruct",
            description="Model name for regeneration"
        )
        max_retries: int = Field(
            default=3,
            description="Maximum retry attempts for code regeneration"
        )
        enable_auto_fix: bool = Field(
            default=True,
            description="Enable automatic code regeneration on syntax errors"
        )
        context_length: int = Field(
            default=32768,
            description="Model's maximum context length"
        )
        min_response_tokens: int = Field(
            default=2048,
            description="Minimum tokens reserved for response"
        )

    def __init__(self):
        self.valves = self.Valves()
        os.makedirs(self.valves.temp_dir, exist_ok=True)

    def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> Union[str, Generator, Iterator]:
        """Pipe that checks Verilog syntax and auto-regenerates on errors."""
        messages = body.get("messages", [])
        if not messages:
            return self._call_llm(body)
        
        # Get initial LLM response
        response = self._call_llm(body)
        
        if not self.valves.enable_auto_fix:
            return response
        
        # Check for Verilog code
        code_blocks = self._extract_verilog_blocks(response)
        if not code_blocks:
            return response
        
        # Check syntax
        all_passed = True
        error_details = []
        
        for i, code in enumerate(code_blocks):
            module_name = self._extract_module_name(code) or f"block_{i+1}"
            has_error, error_msg = self._check_syntax(code, module_name)
            if has_error:
                all_passed = False
                error_details.append({"module": module_name, "code": code, "error": error_msg})
        
        if all_passed:
            return response + "\n\n---\n✅ **Syntax Check**: All code passed Verilator verification."
        
        # Auto-regenerate on errors
        return self._auto_regenerate(body, messages, error_details, response)

    def _estimate_tokens(self, messages: List[dict]) -> int:
        """Rough token estimation (4 chars ~= 1 token)."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4

    def _truncate_messages(self, messages: List[dict], max_messages: int = 6) -> List[dict]:
        """Keep system + last N messages to reduce context."""
        if len(messages) <= max_messages:
            return messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        return system_msgs + other_msgs[-(max_messages - len(system_msgs)):]

    def _call_llm(self, body: dict, truncate: bool = False) -> str:
        """Call LLM API with dynamic max_tokens."""
        try:
            messages = body.get("messages", [])
            if truncate:
                messages = self._truncate_messages(messages)
            
            # Calculate available tokens
            input_tokens = self._estimate_tokens(messages)
            available = self.valves.context_length - input_tokens
            max_tokens = max(self.valves.min_response_tokens, min(available - 100, 4096))
            
            if max_tokens < self.valves.min_response_tokens:
                return f"Error: Context too long ({input_tokens} tokens). Please start a new conversation."
            
            resp = requests.post(
                self.valves.llm_api_url,
                json={
                    "model": self.valves.model_name,
                    "messages": messages,
                    "temperature": body.get("temperature", 0.7),
                    "max_tokens": max_tokens,
                },
                timeout=120
            )
            if resp.status_code == 200:
                return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            elif resp.status_code == 400 and ("input tokens" in resp.text or "context length" in resp.text):
                # Context overflow - conversation too long
                return "⚠️ **Conversation too long!**\n\nThe conversation has exceeded the model's context limit. Please create a new chat to continue."
            elif resp.status_code == 400 and "max_tokens" in resp.text:
                # Token calculation error - try with truncation
                if not truncate:
                    return self._call_llm(body, truncate=True)
                return "⚠️ **Context overflow.** Please start a new conversation."
            return f"Error: {resp.status_code} - {resp.text}"
        except Exception as e:
            return f"Error: {str(e)}"

    def _auto_regenerate(self, body: dict, original_messages: List[dict], 
                         error_details: List[dict], original_response: str) -> str:
        """Auto-regenerate code with error fixes."""
        error_summary = "\n".join([
            f"**`{e['module']}`**: {e['error']}" for e in error_details
        ])
        
        fix_prompt = (
            "The Verilog code has syntax errors:\n\n"
            f"{error_summary}\n\n"
            "Please regenerate the corrected Verilog code with:\n"
            "1. All syntax errors fixed\n"
            "2. Proper module declarations\n"
            "3. Verilog-2001 syntax\n"
            "4. Complete and correct code only"
        )
        
        new_messages = original_messages.copy()
        new_messages.append({"role": "assistant", "content": original_response})
        new_messages.append({"role": "user", "content": fix_prompt})
        
        retry_count = 0
        current_messages = new_messages
        new_errors = error_details
        
        while retry_count < self.valves.max_retries:
            retry_count += 1
            
            new_body = body.copy()
            new_body["messages"] = current_messages
            new_response = self._call_llm(new_body)
            
            new_code_blocks = self._extract_verilog_blocks(new_response)
            if not new_code_blocks:
                return (
                    f"⚠️ **Retry {retry_count}/{self.valves.max_retries}**: No Verilog code found.\n\n"
                    f"**Errors:**\n{error_summary}\n\n"
                    f"**Response:**\n{new_response}"
                )
            
            # Check new code
            new_errors = []
            for i, code in enumerate(new_code_blocks):
                module_name = self._extract_module_name(code) or f"block_{i+1}"
                has_error, error_msg = self._check_syntax(code, module_name)
                if has_error:
                    new_errors.append({"module": module_name, "code": code, "error": error_msg})
            
            if not new_errors:
                return (
                    f"✅ **Code regenerated and verified!** (Attempt {retry_count})\n\n"
                    f"{new_response}\n\n"
                    "---\n✅ **Syntax Check**: Passed Verilator verification."
                )
            
            # Prepare next retry
            if retry_count < self.valves.max_retries:
                err_str = "\n".join([f"**`{e['module']}`**: {e['error']}" for e in new_errors])
                current_messages = new_messages.copy()
                current_messages.append({"role": "assistant", "content": new_response})
                current_messages.append({"role": "user", "content": f"Still has errors:\n{err_str}\n\nPlease fix."})
        
        # Max retries reached
        err_list = "\n".join([f"- `{e['module']}`: {e['error'][:80]}..." for e in new_errors])
        return (
            f"⚠️ **Max retries reached ({self.valves.max_retries})**\n\n"
            f"Remaining errors:\n{err_list}\n\n"
            f"**Last response:**\n{new_response}\n\n"
            "Please manually fix the remaining issues."
        )

    def _extract_verilog_blocks(self, text: str) -> List[str]:
        """Extract Verilog code blocks."""
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
        """Extract module name."""
        match = re.search(r'module\s+(\w+)', code, re.IGNORECASE)
        return match.group(1) if match else None

    def _check_syntax(self, code: str, module_name: str) -> tuple[bool, str]:
        """Check syntax with Verilator. Returns (has_error, error_message)."""
        file_path = os.path.join(self.valves.temp_dir, f"{module_name}.v")
        
        try:
            with open(file_path, "w") as f:
                f.write(code)
        except Exception as e:
            return (True, f"Save failed: {e}")
        
        try:
            result = subprocess.run(
                [self.valves.verilator_path, "--lint-only", file_path],
                capture_output=True, text=True, timeout=60
            )
            output = (result.stderr + result.stdout).strip()
            
            # Filter info messages
            lines = [l for l in output.split('\n') 
                    if l.strip() and not any(x in l.replace(' ','') 
                    for x in ['VerilationReport','Verilator:','-Verilator'])]
            filtered = '\n'.join(lines).strip()
            
            if result.returncode == 0:
                return (False, "")
            return (True, filtered)
            
        except subprocess.TimeoutExpired:
            return (True, "Timeout")
        except FileNotFoundError:
            return (True, "Verilator not found")

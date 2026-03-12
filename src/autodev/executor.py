"""Task executors for the autonomous development loop.

Provides different backends for actually implementing tasks:
- DryRunExecutor: Just prints the prompt (for testing)
- ClaudeAPIExecutor: Calls the Claude API to implement tasks
- ClaudeCodeExecutor: Shells out to `claude` CLI for implementation
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    """Result of executing a task, including token usage."""

    success: bool
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __bool__(self) -> bool:
        """Allow using ExecutionResult as a boolean for backward compatibility."""
        return self.success


class DryRunExecutor:
    """Executor that prints prompts without implementing anything."""

    def __call__(self, prompt: str, project_root: Path) -> ExecutionResult:
        print(f"  [DRY RUN] Would execute prompt ({len(prompt)} chars)")
        return ExecutionResult(success=True)


class ClaudeCodeExecutor:
    """Executor that uses the `claude` CLI to implement tasks.

    Invokes `claude --print` with the task prompt, letting Claude Code
    handle file reading, editing, and tool use autonomously.
    """

    def __init__(
        self,
        *,
        max_turns: int = 25,
        model: str | None = None,
        timeout_seconds: int = 600,
    ):
        self.max_turns = max_turns
        self.model = model
        self.timeout_seconds = timeout_seconds

    def __call__(self, prompt: str, project_root: Path) -> ExecutionResult:
        cmd = [
            "claude",
            "--print",
            "--output-format",
            "json",
            "--max-turns",
            str(self.max_turns),
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        # Pass the prompt via stdin
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            input_tokens, output_tokens = self._parse_token_usage(result.stdout)
            if result.returncode == 0:
                print("  Claude Code completed successfully")
                return ExecutionResult(
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            else:
                print(f"  Claude Code failed (exit {result.returncode})")
                if result.stderr:
                    print(f"  stderr: {result.stderr[:500]}")
                return ExecutionResult(
                    success=False,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
        except subprocess.TimeoutExpired:
            print(f"  Claude Code timed out after {self.timeout_seconds}s")
            return ExecutionResult(success=False)
        except FileNotFoundError:
            print("  Error: `claude` CLI not found. Install Claude Code first.")
            return ExecutionResult(success=False)

    @staticmethod
    def _parse_token_usage(output: str) -> tuple[int, int]:
        """Parse token usage from claude CLI JSON output.

        When --output-format json is used, the response includes
        usage stats. Returns (input_tokens, output_tokens).
        """
        try:
            data = json.loads(output)
            usage = data.get("usage", {})
            return (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        except (json.JSONDecodeError, AttributeError):
            return 0, 0


class ClaudeAPIExecutor:
    """Executor that calls the Anthropic API directly.

    Uses the Anthropic Python SDK to send the task prompt to Claude
    and apply the response. Requires ANTHROPIC_API_KEY env var.
    """

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 16384,
    ):
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, prompt: str, project_root: Path) -> ExecutionResult:
        try:
            import anthropic
        except ImportError:
            print("  Error: anthropic package not installed. Run: uv add anthropic")
            return ExecutionResult(success=False)

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  Error: ANTHROPIC_API_KEY not set")
            return ExecutionResult(success=False)

        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = (
            "You are an autonomous developer working on the SBIR Analytics project. "
            "Implement the requested task by outputting a series of file operations. "
            "Format each operation as a JSON object on its own line:\n"
            '{"action": "edit", "file": "path/to/file.py", "search": "old code", "replace": "new code"}\n'
            '{"action": "create", "file": "path/to/new.py", "content": "file content"}\n'
            "Only output JSON operations, no other text."
        )

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract token usage from response
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Parse and apply operations
            text = response.content[0].text
            applied = 0
            for line in text.strip().splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    op = json.loads(line)
                    if self._apply_operation(op, project_root):
                        applied += 1
                except (json.JSONDecodeError, KeyError):
                    continue

            print(f"  Applied {applied} operations from Claude API response")
            print(f"  Tokens: {input_tokens:,} in / {output_tokens:,} out")
            return ExecutionResult(
                success=applied > 0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            print(f"  API error: {e}")
            return ExecutionResult(success=False)

    def _apply_operation(self, op: dict, project_root: Path) -> bool:
        """Apply a single file operation.

        Validates that resolved paths stay within project_root to prevent
        path traversal attacks from model output.
        """
        action = op.get("action")
        raw_path = op.get("file", "")
        filepath = (project_root / raw_path).resolve()

        # Security: ensure resolved path is within project_root
        try:
            filepath.relative_to(project_root.resolve())
        except ValueError:
            print(f"  BLOCKED: path traversal attempt: {raw_path}")
            return False

        # Restrict writes to src/ and tests/ directories
        rel = str(filepath.relative_to(project_root.resolve()))
        if not (rel.startswith("src/") or rel.startswith("tests/")):
            print(f"  BLOCKED: writes only allowed to src/ and tests/: {rel}")
            return False

        if action == "create":
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(op["content"], encoding="utf-8")
            return True

        elif action == "edit":
            if not filepath.exists():
                return False
            content = filepath.read_text(encoding="utf-8")
            search = op.get("search", "")
            replace = op.get("replace", "")
            if search in content:
                content = content.replace(search, replace, 1)
                filepath.write_text(content, encoding="utf-8")
                return True

        return False

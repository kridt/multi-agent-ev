"""Abstract base class for Claude-powered agents.

Extracts the common patterns from Orchestrator and AnomalyReasoner into a
reusable base:
- Anthropic client initialisation
- Conversation history management
- The tool-use loop (send message -> process tool_use blocks -> send results -> repeat)
- History trimming

Subclasses must implement:
- system_prompt (property): the system prompt that defines the agent's role
- tools (property): the list of tool definitions exposed to Claude
- execute_tool(tool_name, tool_input): dispatches a tool call to the right function

Design decisions:
- The tool-use loop has a hard cap (max_iterations) to prevent runaway API spend.
- If a tool call raises an exception, an is_error=True tool_result is sent back
  so Claude can handle it gracefully rather than crashing the loop.
- Conversation history is kept in memory and trimmed to max_history messages
  to avoid growing context unboundedly across calls.
- The base class does NOT assume any particular tool set or domain. It is
  purely mechanical: call Claude, process tool_use, repeat.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from config.settings import settings

logger = logging.getLogger(__name__)

# Default model for all agents. Subclasses may override via constructor.
DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

# Default hard cap on tool-use loop iterations.
DEFAULT_MAX_ITERATIONS: int = 10

# Default max tokens for Claude responses.
DEFAULT_MAX_TOKENS: int = 2048


class BaseAgent(ABC):
    """Abstract base class for Claude-powered agents.

    Usage (subclass)::

        class MyAgent(BaseAgent):
            @property
            def system_prompt(self) -> str:
                return "You are a helpful assistant."

            @property
            def tools(self) -> list[dict]:
                return [...]

            async def execute_tool(self, tool_name, tool_input):
                ...

        agent = MyAgent(name="my-agent")
        response = await agent.run("Hello!")
    """

    def __init__(
        self,
        name: str,
        model: str = DEFAULT_MODEL,
        max_history: int = 50,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.name = name
        self.model = model
        self.max_history = max_history
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._history: list[dict[str, Any]] = []
        self._logger = logging.getLogger(f"{__name__}.{name}")

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt that defines this agent's role."""
        ...

    @property
    @abstractmethod
    def tools(self) -> list[dict]:
        """Return the list of Anthropic tool definitions for this agent.

        Return an empty list if the agent does not use tools.
        """
        ...

    @abstractmethod
    async def execute_tool(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> Any:
        """Execute a tool call and return the result.

        The result will be JSON-serialised and sent back to Claude as a
        tool_result content block. If the tool raises an exception, the
        base class catches it and sends an is_error=True result.

        Args:
            tool_name: The name of the tool Claude requested.
            tool_input: The input dict Claude provided.

        Returns:
            Any JSON-serialisable value.
        """
        ...

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Run the main tool-use loop.

        Sends the user_message (optionally enriched with context) to Claude,
        processes any tool_use blocks by calling execute_tool(), sends results
        back, and repeats until Claude responds with end_turn or the iteration
        cap is hit.

        Args:
            user_message: The user message to send to Claude.
            context: Optional context dict. If provided, it is appended to the
                user message as a JSON block so Claude has the full picture.

        Returns:
            The final text response from Claude.
        """
        # Build the user content.
        content = user_message
        if context:
            content += f"\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

        # Add user message to history.
        self._history.append({"role": "user", "content": content})
        self._trim_history()

        iteration = 0
        tool_kwargs = {"tools": self.tools} if self.tools else {}

        while iteration < self.max_iterations:
            iteration += 1

            try:
                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    messages=self._history,
                    **tool_kwargs,
                )
            except anthropic.APIError as exc:
                self._logger.error(
                    "%s: Claude API error in tool loop — %s", self.name, exc
                )
                return f"[ERROR] Claude API error: {exc}"

            # Add Claude's response to history.
            self._history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract the final text block.
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            if response.stop_reason != "tool_use":
                self._logger.warning(
                    "%s: unexpected stop_reason %r — stopping loop",
                    self.name,
                    response.stop_reason,
                )
                # Try to extract any text from the response.
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                break

            # Execute all tool_use blocks in this response.
            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_result = await self._dispatch_tool(
                    tool_name=block.name,
                    tool_input=block.input,
                    tool_use_id=block.id,
                )
                tool_results.append(tool_result)

            # Feed tool results back to Claude.
            self._history.append({"role": "user", "content": tool_results})

        self._logger.warning(
            "%s: tool loop hit iteration cap (%d) — returning partial result",
            self.name,
            self.max_iterations,
        )
        return "[PARTIAL] Tool loop iteration cap reached."

    def reset(self) -> None:
        """Clear conversation history."""
        self._history.clear()
        self._logger.debug("%s: conversation history cleared", self.name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        """Keep history within the max_history limit.

        Removes the oldest messages (from the front) to stay within bounds.
        Always removes in pairs (user + assistant) to keep the conversation
        structure valid, unless there is an odd number — then we just trim
        from the front.
        """
        while len(self._history) > self.max_history:
            self._history.pop(0)

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        """Dispatch a single tool call and return an Anthropic tool_result block.

        If execute_tool raises an exception, returns is_error=True so Claude
        can handle degraded data gracefully rather than crashing the loop.
        """
        self._logger.debug(
            "%s: tool call %r with input %s", self.name, tool_name, tool_input
        )

        try:
            result = await self.execute_tool(tool_name, tool_input)
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result, default=str),
            }
        except Exception as exc:
            self._logger.error(
                "%s: tool %r raised %s — %s",
                self.name,
                tool_name,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "is_error": True,
                "content": f"Tool error: {type(exc).__name__}: {exc}",
            }

"""In-process async message bus for agent-to-agent communication.

This is NOT a heavyweight message broker. It is a simple asyncio.Queue-based
routing system designed for a single-process deployment where the orchestrator
and anomaly reasoner (and any future agents) need to exchange messages.

Design decisions:
- Each registered agent gets its own asyncio.Queue. Messages are routed by
  the to_agent field on the AgentMessage dataclass.
- broadcast() sends to all registered agents except the sender.
- An optional message_types filter on register() allows an agent to only
  receive certain message types (e.g., only ALERTs).
- A bounded message log (deque) keeps the last N messages for debugging /
  dashboard display. The log is not persisted — it exists only in memory.
- get_message() uses asyncio.wait_for with a timeout so callers never block
  indefinitely.
- The module exports a singleton `message_bus` instance for convenience.
  All agents in the process share this single bus.

Assumptions:
- All agents run in the same asyncio event loop (single process).
- Message payloads are plain dicts (JSON-serialisable).
- Queue sizes are unbounded. In practice, agents should consume messages
  promptly. If an agent falls behind, messages accumulate in memory.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages that agents can exchange."""

    REQUEST = "request"
    RESPONSE = "response"
    ALERT = "alert"
    INFO = "info"


@dataclass
class AgentMessage:
    """A message exchanged between agents.

    Attributes:
        id: Unique message identifier.
        from_agent: Name of the sending agent.
        to_agent: Name of the target agent (or "*" for broadcast — set internally).
        message_type: The type of message.
        payload: Arbitrary dict payload.
        timestamp: When the message was created (UTC).
        correlation_id: Optional ID for request/response pairing. When an agent
            sends a REQUEST, it sets a correlation_id. The responding agent
            includes the same correlation_id in its RESPONSE so the requester
            can match them up.
    """

    from_agent: str
    to_agent: str
    message_type: MessageType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for logging / dashboard display."""
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }


class MessageBus:
    """In-process async message bus for agent communication.

    Usage::

        bus = MessageBus()
        bus.register("orchestrator")
        bus.register("anomaly_reasoner", message_types=[MessageType.REQUEST])

        # Send a message
        msg = AgentMessage(
            from_agent="orchestrator",
            to_agent="anomaly_reasoner",
            message_type=MessageType.REQUEST,
            payload={"signal_id": "abc123"},
        )
        await bus.publish(msg)

        # Receive
        received = await bus.get_message("anomaly_reasoner", timeout=5.0)
    """

    def __init__(self, log_size: int = 200) -> None:
        # agent_name -> asyncio.Queue
        self._queues: dict[str, asyncio.Queue[AgentMessage]] = {}
        # agent_name -> set of MessageType (None = accept all)
        self._filters: dict[str, set[MessageType] | None] = {}
        # Bounded message log for debugging.
        self._log: deque[dict[str, Any]] = deque(maxlen=log_size)

    def register(
        self,
        agent_name: str,
        message_types: list[MessageType] | None = None,
    ) -> None:
        """Register an agent with the message bus.

        Args:
            agent_name: Unique name for this agent.
            message_types: Optional list of MessageType values this agent
                wants to receive. If None, the agent receives all types.
        """
        if agent_name in self._queues:
            logger.warning("MessageBus: agent %r already registered — skipping", agent_name)
            return

        self._queues[agent_name] = asyncio.Queue()
        self._filters[agent_name] = set(message_types) if message_types else None
        logger.info(
            "MessageBus: registered agent %r (filter=%s)",
            agent_name,
            [mt.value for mt in message_types] if message_types else "all",
        )

    def unregister(self, agent_name: str) -> None:
        """Remove an agent from the bus."""
        self._queues.pop(agent_name, None)
        self._filters.pop(agent_name, None)
        logger.info("MessageBus: unregistered agent %r", agent_name)

    async def publish(self, message: AgentMessage) -> None:
        """Route a message to the target agent's queue.

        If the target agent is not registered or has filtered out this
        message type, the message is logged but silently dropped.
        """
        self._log.append(message.to_dict())

        target = message.to_agent
        if target not in self._queues:
            logger.warning(
                "MessageBus: target agent %r not registered — dropping message %s",
                target,
                message.id,
            )
            return

        # Check filter.
        agent_filter = self._filters.get(target)
        if agent_filter is not None and message.message_type not in agent_filter:
            logger.debug(
                "MessageBus: message type %s filtered out for agent %r — dropping",
                message.message_type.value,
                target,
            )
            return

        await self._queues[target].put(message)
        logger.debug(
            "MessageBus: delivered message %s from %s to %s (type=%s)",
            message.id,
            message.from_agent,
            target,
            message.message_type.value,
        )

    async def broadcast(
        self,
        from_agent: str,
        message_type: MessageType,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        """Send a message to all registered agents except the sender.

        Creates a separate AgentMessage for each recipient so each gets
        its own message ID and to_agent field.
        """
        for agent_name in list(self._queues.keys()):
            if agent_name == from_agent:
                continue

            msg = AgentMessage(
                from_agent=from_agent,
                to_agent=agent_name,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )
            await self.publish(msg)

    async def get_message(
        self,
        agent_name: str,
        timeout: float = 1.0,
    ) -> AgentMessage | None:
        """Get the next message for an agent, with timeout.

        Args:
            agent_name: The agent requesting its next message.
            timeout: Maximum seconds to wait. Default 1.0.

        Returns:
            The next AgentMessage, or None if the timeout expired or the
            agent is not registered.
        """
        queue = self._queues.get(agent_name)
        if queue is None:
            logger.warning("MessageBus: get_message for unregistered agent %r", agent_name)
            return None

        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def get_messages(
        self,
        agent_name: str,
        max_messages: int = 10,
    ) -> list[AgentMessage]:
        """Get all pending messages for an agent (non-blocking).

        Drains up to max_messages from the agent's queue without waiting.

        Args:
            agent_name: The agent requesting its messages.
            max_messages: Maximum number of messages to return.

        Returns:
            List of AgentMessage objects (may be empty).
        """
        queue = self._queues.get(agent_name)
        if queue is None:
            logger.warning("MessageBus: get_messages for unregistered agent %r", agent_name)
            return []

        messages: list[AgentMessage] = []
        count = 0
        while count < max_messages:
            try:
                msg = queue.get_nowait()
                messages.append(msg)
                count += 1
            except asyncio.QueueEmpty:
                break

        return messages

    def get_log(
        self,
        limit: int = 50,
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent message log entries.

        Args:
            limit: Maximum number of entries to return.
            agent: Optional filter — only return messages where from_agent
                or to_agent matches this value.

        Returns:
            List of message dicts (most recent last), capped at limit.
        """
        entries = list(self._log)

        if agent:
            entries = [
                e for e in entries
                if e.get("from_agent") == agent or e.get("to_agent") == agent
            ]

        # Return the most recent `limit` entries.
        return entries[-limit:]

    @property
    def registered_agents(self) -> list[str]:
        """Return names of all registered agents."""
        return list(self._queues.keys())

    def pending_count(self, agent_name: str) -> int:
        """Return the number of pending messages for an agent."""
        queue = self._queues.get(agent_name)
        if queue is None:
            return 0
        return queue.qsize()


# Module-level singleton — all agents in the process share this bus.
message_bus = MessageBus()

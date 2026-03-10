"""Agents package.

Exports:
- BaseAgent: abstract base class for Claude-powered agents.
- Orchestrator: main scan-cycle and daily-report agent.
- AnomalyReasoner: Claude-powered signal anomaly assessment agent.
- MessageBus: in-process async message bus for agent communication.
- AgentMessage: dataclass representing a message between agents.
- MessageType: enum for message types (REQUEST, RESPONSE, ALERT, INFO).
"""

from agents.base_agent import BaseAgent
from agents.anomaly_reasoner import AnomalyReasoner
from agents.message_bus import AgentMessage, MessageBus, MessageType
from agents.orchestrator import Orchestrator

__all__ = [
    "BaseAgent",
    "Orchestrator",
    "AnomalyReasoner",
    "MessageBus",
    "AgentMessage",
    "MessageType",
]

"""
conversation_log.py
-------------------
Append-only immutable debate log.
Each entry records: timestamp, agent name, content, round number.
No update/delete — this is an audit trail.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """A single immutable log entry in the debate."""
    timestamp: str
    agent: str
    content: str
    round_num: int
    entry_type: str = "argument"  # "argument", "review", "verdict"

    def to_dict(self) -> dict:
        return asdict(self)


class ConversationLog:
    """
    Append-only immutable conversation log.
    Once an entry is added, it cannot be modified or deleted.
    """

    def __init__(self):
        self._entries: list[LogEntry] = []
        self._frozen = False

    def add_entry(
        self,
        agent: str,
        content: str,
        round_num: int,
        entry_type: str = "argument",
    ) -> LogEntry:
        """Add a new entry to the log. Returns the created entry."""
        if self._frozen:
            raise RuntimeError("Log is frozen — cannot add entries after verdict.")

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            content=content,
            round_num=round_num,
            entry_type=entry_type,
        )
        self._entries.append(entry)
        logger.debug("Log entry added: [Round %d] %s (%s)", round_num, agent, entry_type)
        return entry

    def freeze(self):
        """Freeze the log — no more entries can be added."""
        self._frozen = True

    @property
    def entries(self) -> list[LogEntry]:
        """Return a copy of all entries (immutable view)."""
        return list(self._entries)

    @property
    def round_count(self) -> int:
        """Number of completed debate rounds."""
        if not self._entries:
            return 0
        return max(e.round_num for e in self._entries)

    def get_round(self, round_num: int) -> list[LogEntry]:
        """Get all entries for a specific round."""
        return [e for e in self._entries if e.round_num == round_num]

    def get_agent_entries(self, agent: str) -> list[LogEntry]:
        """Get all entries by a specific agent."""
        return [e for e in self._entries if e.agent == agent]

    def to_dict_list(self) -> list[dict]:
        """Export all entries as a list of dicts."""
        return [e.to_dict() for e in self._entries]

    def export_to_markdown(self) -> str:
        """Export the debate log as formatted markdown."""
        if not self._entries:
            return "# Debate Log\n\n*No debate entries recorded.*"

        lines = ["# Debate Log", ""]

        current_round = -1
        for entry in self._entries:
            if entry.round_num != current_round:
                current_round = entry.round_num
                if entry.entry_type == "verdict":
                    lines.append(f"## 🏛️ Final Verdict")
                else:
                    lines.append(f"## Round {current_round}")
                lines.append("")

            agent_emoji = {
                "advocate": "🟢",
                "critic": "🔴",
                "fairness": "🔵",
                "orchestrator": "⚖️",
            }.get(entry.agent, "📝")

            lines.append(f"### {agent_emoji} {entry.agent.title()}")
            lines.append(f"*{entry.timestamp}*")
            lines.append("")
            lines.append(entry.content)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize the full log as JSON."""
        return json.dumps(self.to_dict_list(), indent=2, ensure_ascii=False)

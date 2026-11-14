#!/usr/bin/env python3
"""Evidence exploration layer for https://github.com/ucla-cs188-fall26/blindata.

Drop this file beside checker.py. It imports checker.load(), checker.facts(), and
checker.check() without changing the constraint logic or existing CLI.

LLM mode uses read-only function tools provided by llm_agent.py when
OPENAI_API_KEY is configured. Without a key, the original deterministic
question router remains available for offline testing and demonstrations.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

GROUPS = ("contradicted", "missing", "unverifiable", "verified")
MONTHS = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "may": "may", "jun": "june", "jul": "july", "aug": "august",
    "sep": "september", "sept": "september", "oct": "october",
    "nov": "november", "dec": "december",
}


def _words(text: str, needle: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(needle.lower()) + r"(?!\w)", text.lower()))


def _fmt(value: float) -> str:
    return f"{value:g}"


@dataclass(frozen=True)
class Finding:
    id: int
    status: str
    message: str
    kind: str
    series: str | None


class EvidenceAgent:
    """A read-only conversational explorer for the checker.py result."""

    def __init__(
        self,
        labels: list[str],
        series: dict[str, list[float]],
        unit: str | None,
        description: str,
        buckets: dict[str, list[str]],
    ) -> None:
        if not labels or not series:
            raise ValueError("At least one label and one data series are required.")
        if any(len(values) != len(labels) for values in series.values()):
            raise ValueError("All data series must have the same length as labels.")
        self.labels = labels
        self.series = series
        self.unit = unit
        self.description = description
        self.buckets = buckets
        self.findings: list[Finding] = []
        for status in GROUPS:
            for msg in buckets.get(status, []):
                kind = self._kind(msg, status)
                affected = self._series_in(msg)
                self.findings.append(Finding(
                    id=len(self.findings) + 1,
                    status=status,
                    message=msg,
                    kind=kind,
                    series=affected,
                ))
        self.active_id = next((f.id for f in self.findings if f.status == "contradicted"),
                              self.findings[0].id if self.findings else None)
        self._llm_agent = None

    @classmethod
    def from_files(cls, data_file: str | Path, description_file: str | Path) -> "EvidenceAgent":
        # Import lazily so unit tests can check this adapter without copying checker.py.
        from checker import DEFAULT_UNIT, check, facts, load
        labels, series, unit = load(data_file)
        description = Path(description_file).read_text(encoding="utf-8")
        buckets = check(description, labels, series, facts(labels, series), unit or DEFAULT_UNIT)
        return cls(labels, series, unit, description, buckets)

    def _series_in(self, text: str) -> str | None:
        for name in sorted(self.series, key=len, reverse=True):
            if _words(text, name):
                return name
        return None

    @staticmethod
    def _kind(message: str, status: str) -> str:
        if status == "missing":
            return "completeness"
        prefix = message.partition(":")[0].strip().lower()
        return {"trend": "trend", "values": "value", "peak": "maximum",
                "units": "unit"}.get(prefix, "claim")

    def _selected(self) -> Finding | None:
        return next((f for f in self.findings if f.id == self.active_id), None)

    def _find_by_kind(self, text: str) -> Finding | None:
        category = (
            "trend" if re.search(r"trend|increas|decreas|ris|fall|fell|grow", text) else
            "maximum" if re.search(r"peak|max|min|highest|lowest", text) else
            "unit" if re.search(r"unit|axis", text) else
            "value" if re.search(r"number|value", text) else
            "completeness" if re.search(r"miss|omit|series", text) else None
        )
        if category:
            return next((f for f in self.findings if f.kind == category and
                         f.status in ("contradicted", "missing")), None)
        return None

    def _series_choice(self, question: str) -> str | None:
        explicit = self._series_in(question)
        if explicit:
            return explicit
        selected = self._selected()
        if selected and selected.series:
            return selected.series
        return next(iter(self.series)) if len(self.series) == 1 else None

    def _label_mentions(self, question: str) -> list[str]:
        mentions = []
        for label in self.labels:
            if _words(question, label):
                mentions.append(label)
                continue
            lower = label.lower()
            canonical = MONTHS.get(lower, lower)
            alternatives = [k for k, v in MONTHS.items() if v == canonical] + [canonical]
            if any(_words(question, variant) for variant in alternatives):
                mentions.append(label)
        return mentions

    def _rows(self, series: str, labels: list[str] | None = None) -> list[dict[str, Any]]:
        targets = set(labels) if labels is not None else set(self.labels)
        return [{"label": label, "series": series, "value": value,
                 "row_index": i + 1}
                for i, (label, value) in enumerate(zip(self.labels, self.series[series]))
                if label in targets]

    def _result(self, answer: str, evidence: list[dict[str, Any]] | None = None,
                finding: Finding | None = None) -> dict[str, Any]:
        return {"answer": answer, "evidence": evidence or [],
                "finding": asdict(finding) if finding else None}

    def summary(self) -> dict[str, Any]:
        counts = {name: len(self.buckets.get(name, [])) for name in GROUPS}
        parts = [f"Verification results: {counts['contradicted']} contradicted; "
                 f"{counts['missing']} potentially missing; "
                 f"{counts['unverifiable']} unverifiable; "
                 f"{counts['verified']} verified."]
        if self.findings:
            parts.append("Findings:")
            for item in self.findings:
                parts.append(f"{item.id}. [{item.status}] {item.message}")
            parts.append("Ask 'why 1', 'show evidence', 'compare Feb and Mar', or 'corrected description'.")
        else:
            parts.append("No findings were reported. This is not proof that every chart claim is correct.")
        return self._result("\n".join(parts))

    def inspect(self, finding_id: int | None = None) -> dict[str, Any]:
        if finding_id is not None:
            if not any(f.id == finding_id for f in self.findings):
                return self._result(f"Finding {finding_id} does not exist. Ask for 'summary' to see the list.")
            self.active_id = finding_id
        finding = self._selected()
        if not finding:
            return self._result("No findings are available to inspect.")
        lines = [f"Finding {finding.id}: {finding.status}. {finding.message}"]
        rows: list[dict[str, Any]] = []
        if finding.kind == "unit":
            if self.unit:
                lines.append(f"Reference chart axis unit: {self.unit}.")
            else:
                lines.append("The source file has no unit metadata; units cannot be independently confirmed.")
        elif finding.series:
            rows = self._rows(finding.series)
            if finding.kind == "maximum":
                extreme = max(self.series[finding.series])
                labels = [label for label, value in zip(self.labels, self.series[finding.series])
                          if value == extreme]
                lines.append(f"Source maximum for {finding.series}: {_fmt(extreme)} at {', '.join(labels)}.")
            elif finding.kind == "trend":
                vals = self.series[finding.series]
                direction = "rises" if vals[-1] > vals[0] else "falls" if vals[-1] < vals[0] else "is flat"
                lines.append(f"Source series {finding.series} {direction} overall: {_fmt(vals[0])} to {_fmt(vals[-1])}.")
                drops = [(self.labels[i - 1], self.labels[i], vals[i - 1], vals[i])
                         for i in range(1, len(vals)) if vals[i] < vals[i - 1]]
                if drops:
                    first = drops[0]
                    lines.append(f"Example decrease: {first[0]} {_fmt(first[2])} to {first[1]} {_fmt(first[3])}.")
            else:
                lines.append(f"Source values for series {finding.series} are listed as evidence.")
        else:
            lines.append("This finding does not identify a specific series. You can inspect the entire dataset or name a series.")
        if rows:
            lines.append("Source data: " + "; ".join(f"{r['label']} {_fmt(r['value'])}" for r in rows[:40])
                         + ("; additional rows omitted" if len(rows) > 40 else ""))
        return self._result("\n".join(lines), rows, finding)

    def compare(self, question: str) -> dict[str, Any]:
        labels = self._label_mentions(question)
        series = self._series_choice(question)
        if not series:
            return self._result("Which data series would you like to compare? Say its name.")
        if len(labels) != 2:
            return self._result("Please name exactly two categories, for example 'compare February and March'.")
        first, second = labels
        a = self.series[series][self.labels.index(first)]
        b = self.series[series][self.labels.index(second)]
        change = f"{((b-a)/a)*100:.1f}%" if a else "undefined (initial value is zero)"
        rows = self._rows(series, labels)
        return self._result(f"For {series}, {first} is {_fmt(a)} and {second} is {_fmt(b)}. "
                            f"Change from {first} to {second}: {_fmt(b-a)}; percentage change: {change}.", rows)

    def source_values(self, question: str) -> dict[str, Any]:
        series = self._series_choice(question)
        if not series:
            return self._result("Please specify the series name. Available series: " + ", ".join(self.series))
        labels = self._label_mentions(question)
        rows = self._rows(series, labels if labels else None)
        shown = rows[:50]
        answer = f"Original source values for {series}: " + "; ".join(
            f"{r['label']} {_fmt(r['value'])}" for r in shown)
        if len(rows) > len(shown):
            answer += f". {len(rows) - len(shown)} more values not spoken."
        return self._result(answer, rows)

    def extrema(self, question: str) -> dict[str, Any]:
        series = self._series_choice(question)
        if not series:
            return self._result("Please specify the series name to inspect the maximum or minimum.")
        vals = self.series[series]
        maximum, minimum = max(vals), min(vals)
        max_labels = [self.labels[i] for i, v in enumerate(vals) if v == maximum]
        min_labels = [self.labels[i] for i, v in enumerate(vals) if v == minimum]
        return self._result(
            f"For {series}, maximum is {_fmt(maximum)} at {', '.join(max_labels)}; "
            f"minimum is {_fmt(minimum)} at {', '.join(min_labels)}.",
            self._rows(series, max_labels + min_labels),
        )

    def corrected_description(self) -> dict[str, Any]:
        sentences = []
        for name, vals in self.series.items():
            change = "increased" if vals[-1] > vals[0] else "decreased" if vals[-1] < vals[0] else "did not change overall"
            mx, mn = max(vals), min(vals)
            peak = ", ".join(label for label, value in zip(self.labels, vals) if value == mx)
            low = ", ".join(label for label, value in zip(self.labels, vals) if value == mn)
            sentences.append(f"{name} {change} overall from {_fmt(vals[0])} in {self.labels[0]} to "
                             f"{_fmt(vals[-1])} in {self.labels[-1]}. "
                             f"Maximum: {_fmt(mx)} at {peak}. Minimum: {_fmt(mn)} at {low}.")
        prefix = "Suggested data-grounded summary (not the original description): "
        if self.unit:
            prefix += f"Unit: {self.unit}. "
        return self._result(prefix + " ".join(sentences))

    def ask(self, question: str) -> dict[str, Any]:
        """Use LLM tool calling if configured; otherwise preserve the offline router.

        Set BLINDATA_AGENT_MODE=rules to force deterministic operation, or =llm
        to require an API key rather than silently running the rule router.
        """
        mode = os.environ.get("BLINDATA_AGENT_MODE", "auto").lower()
        if mode not in ("auto", "llm", "rules"):
            return self._result("BLINDATA_AGENT_MODE must be auto, llm or rules.")
        if mode == "rules":
            return self._rule_ask(question)
        if not os.environ.get("OPENAI_API_KEY"):
            if mode == "llm":
                return self._result("LLM mode requires OPENAI_API_KEY in the server environment.")
            return self._rule_ask(question)
        try:
            from llm_agent import LLMEvidenceAgent, LLMServiceError
            if self._llm_agent is None:
                self._llm_agent = LLMEvidenceAgent(self)
            return self._llm_agent.ask(question)
        except LLMServiceError as exc:
            # No silent switch to unsupported answers in the event of an outage.
            return self._result(f"LLM unavailable: {exc} Run with BLINDATA_AGENT_MODE=rules for offline commands.")

    def _rule_ask(self, question: str) -> dict[str, Any]:
        q = question.lower().strip()
        if not q:
            return self._result("Please enter a question, or type 'help' for examples.")
        if q in ("help", "?"):
            return self._result("Try: summary; why 1; show evidence; inspect 2; "
                                "show original values for apples; compare Feb and Mar; "
                                "what is the maximum?; corrected description.")
        if re.search(r"\b(summary|all findings|list findings|report|status)\b", q):
            return self.summary()
        id_match = re.search(r"\b(?:finding|issue|item|claim|why|inspect|explain)\s*#?(\d+)\b", q)
        if id_match:
            return self.inspect(int(id_match.group(1)))
        if re.search(r"\b(compare|difference|versus|vs)\b", q):
            return self.compare(q)
        if re.search(r"\b(corrected|correction|correct|rewrite|suggested description|alternative description)\b", q):
            return self.corrected_description()
        if re.search(r"\b(maximum|minimum|highest|lowest)\b", q):
            return self.extrema(q)
        if re.search(r"\b(why|explain|wrong|contradict|missing|discrepancy)\b", q):
            match = self._find_by_kind(q)
            if match:
                return self.inspect(match.id)
            return self.inspect()
        if re.search(r"\b(evidence|inspect|source|original|values|data point|data points)\b", q):
            # If a series is explicitly named, allow direct source inspection.
            if self._series_in(q) or self._label_mentions(q):
                return self.source_values(q)
            return self.inspect()
        if re.search(r"\b(trend|increase|decrease)\b", q):
            match = self._find_by_kind(q)
            return self.inspect(match.id) if match else self.source_values(q)
        return self._result("I can only answer data-grounded questions supported by this prototype. "
                            "Try 'summary', 'why 1', 'show evidence', or 'compare Feb and Mar'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive evidence exploration for blindata")
    parser.add_argument("data_file", help="Existing data file accepted by checker.load()")
    parser.add_argument("description_file", help="Text description to validate")
    args = parser.parse_args()
    agent = EvidenceAgent.from_files(args.data_file, args.description_file)
    print(agent.summary()["answer"])
    print("\nInteractive mode. Type 'help' for commands or 'quit' to exit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit", "q"):
            break
        print("Agent: " + agent.ask(question)["answer"])


if __name__ == "__main__":
    main()

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import csv
import glob

import matplotlib.pyplot as plt
import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
INPUT_PATTERN = "consent_behaviour_*.csv"
COMBINED_FILE = OUTPUT_DIR / "consent_behaviour_combined.csv"
SUMMARY_FILE = OUTPUT_DIR / "consent_behaviour_summary.csv"
GROUPED_SUMMARY_FILE = OUTPUT_DIR / "consent_behaviour_grouped_summary.csv"
PLOT_FILE = OUTPUT_DIR / "consent_behaviour_haptic_analysis.png"

NO_HAPTICS_SESSIONS = {"consent_behaviour_2026_06_02T12_13_00_415Z.csv"}
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

@dataclass
class Event:
    session_id: str
    file_name: str
    event: str
    checkboxId: str
    checkboxLabel: str
    action: str
    timestamp: str
    finalChoice: str
    finalTime: str
    parsed_timestamp: datetime | None = field(init=False)
    parsed_finalTime: datetime | None = field(init=False)

    def __post_init__(self):
        self.parsed_timestamp = parse_timestamp(self.timestamp)
        self.parsed_finalTime = parse_timestamp(self.finalTime)


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, ISO_FORMAT)
    except ValueError:
        return None


def read_sessions() -> list[Event]:
    events: list[Event] = []
    for path in sorted(OUTPUT_DIR.glob(INPUT_PATTERN)):
        if path.name in {COMBINED_FILE.name, SUMMARY_FILE.name, GROUPED_SUMMARY_FILE.name}:
            continue
        session_id = path.stem
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                events.append(
                    Event(
                        session_id=session_id,
                        file_name=path.name,
                        event=row.get("event", ""),
                        checkboxId=row.get("checkboxId", ""),
                        checkboxLabel=row.get("checkboxLabel", ""),
                        action=row.get("action", ""),
                        timestamp=row.get("timestamp", ""),
                        finalChoice=row.get("finalChoice", ""),
                        finalTime=row.get("finalTime", ""),
                    )
                )
    return events


def session_summary(events: list[Event]) -> dict:
    events = sorted(events, key=lambda e: (e.parsed_timestamp or datetime.max, e.event))
    checkbox_actions: dict[str, list[str]] = {}
    checkbox_history: dict[str, list[Event]] = {}
    final_states: dict[str, str] = {}
    first_event_time = None
    final_time = None
    interactions = 0
    for event in events:
        if event.event == "checkbox":
            interactions += 1
            checkbox_actions.setdefault(event.checkboxId, []).append(event.action)
            checkbox_history.setdefault(event.checkboxId, []).append(event)
            if event.parsed_timestamp and first_event_time is None:
                first_event_time = event.parsed_timestamp
            elif event.parsed_timestamp and first_event_time is not None:
                first_event_time = min(first_event_time, event.parsed_timestamp)
        elif event.event == "final" and event.parsed_finalTime:
            final_time = event.parsed_finalTime
    if final_time is None:
        final_time = max((e.parsed_timestamp for e in events if e.parsed_timestamp), default=None)
    for event in events:
        if event.event == "final-state" and event.checkboxId:
            final_states[event.checkboxId] = event.action
    changed_mind = any(len(actions) > 1 for actions in checkbox_actions.values())
    change_count = sum(max(0, len(actions) - 1) for actions in checkbox_actions.values())
    duration_seconds = None
    if first_event_time and final_time:
        duration_seconds = (final_time - first_event_time).total_seconds()

    file_name = events[0].file_name if events else ""
    return {
        "session_id": events[0].session_id if events else "",
        "file_name": file_name,
        "haptic_experience": has_haptic_experience(file_name),
        "start_time": first_event_time.isoformat() + "Z" if first_event_time else "",
        "final_time": final_time.isoformat() + "Z" if final_time else "",
        "duration_seconds": duration_seconds if duration_seconds is not None else "",
        "checkbox_interactions": interactions,
        "changed_mind": changed_mind,
        "change_count": change_count,
        "final_reject_ads": final_states.get("reject-ads", ""),
        "final_reject_analytics": final_states.get("reject-analytics", ""),
        "final_reject_sharing": final_states.get("reject-sharing", ""),
        "final_summary": summarize_final(final_states),
        "changes_by_checkbox": "; ".join(
            f"{checkbox}:{len(actions)}" for checkbox, actions in checkbox_actions.items()
        ),
    }


def has_haptic_experience(file_name: str) -> bool:
    return file_name not in NO_HAPTICS_SESSIONS


def summarize_final(final_states: dict[str, str]) -> str:
    if not final_states:
        return ""
    parts = []
    for key in ["reject-ads", "reject-analytics", "reject-sharing"]:
        value = final_states.get(key, "unknown")
        label = {
            "reject-ads": "ads",
            "reject-analytics": "analytics",
            "reject-sharing": "sharing",
        }[key]
        parts.append(f"{label}={value}")
    return ", ".join(parts)


def write_combined(events: list[Event]) -> None:
    fieldnames = [
        "session_id",
        "file_name",
        "haptic_experience",
        "event",
        "checkboxId",
        "checkboxLabel",
        "action",
        "timestamp",
        "finalChoice",
        "finalTime",
    ]
    with COMBINED_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow({
                "session_id": event.session_id,
                "file_name": event.file_name,
                "haptic_experience": has_haptic_experience(event.file_name),
                "event": event.event,
                "checkboxId": event.checkboxId,
                "checkboxLabel": event.checkboxLabel,
                "action": event.action,
                "timestamp": event.timestamp,
                "finalChoice": event.finalChoice,
                "finalTime": event.finalTime,
            })


def write_summary(summaries: list[dict]) -> None:
    fieldnames = [
        "session_id",
        "file_name",
        "haptic_experience",
        "start_time",
        "final_time",
        "duration_seconds",
        "checkbox_interactions",
        "changed_mind",
        "change_count",
        "changes_by_checkbox",
        "final_reject_ads",
        "final_reject_analytics",
        "final_reject_sharing",
        "final_summary",
    ]
    with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(summary)


def write_grouped_summary(summaries: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for summary in summaries:
        key = "experienced" if summary["haptic_experience"] else "not_experienced"
        groups.setdefault(key, []).append(summary)

    fieldnames = [
        "group_name",
        "haptic_experience",
        "session_count",
        "session_ids",
        "average_duration_seconds",
        "sessions_with_changed_mind",
        "changed_mind_rate",
        "average_change_count",
        "sessions_all_declined",
        "all_declined_rate",
    ]
    with GROUPED_SUMMARY_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for key, group in groups.items():
            count = len(group)
            avg_duration = sum(float(s["duration_seconds"] or 0) for s in group) / count
            changed_count = sum(1 for s in group if s["changed_mind"])
            avg_changes = sum(float(s["change_count"] or 0) for s in group) / count
            final_all_declined = sum(
                1 for s in group if s["final_reject_ads"] == "declined" and s["final_reject_analytics"] == "declined" and s["final_reject_sharing"] == "declined"
            )
            writer.writerow({
                "group_name": "Haptic experienced" if key == "experienced" else "No haptics",
                "haptic_experience": key == "experienced",
                "session_count": count,
                "session_ids": "; ".join(s["session_id"] for s in group),
                "average_duration_seconds": f"{avg_duration:.3f}",
                "sessions_with_changed_mind": changed_count,
                "changed_mind_rate": f"{changed_count/count:.3f}",
                "average_change_count": f"{avg_changes:.2f}",
                "sessions_all_declined": final_all_declined,
                "all_declined_rate": f"{final_all_declined/count:.3f}",
            })


def print_summary(summaries: list[dict]) -> None:
    print(f"Combined file written to: {COMBINED_FILE}")
    print(f"Session summary written to: {SUMMARY_FILE}\n")
    print("Session metrics:")
    for summary in summaries:
        print("-" * 60)
        print(f"Session: {summary['file_name']}")
        print(f"  Start: {summary['start_time']}")
        print(f"  End:   {summary['final_time']}")
        print(f"  Duration (s): {summary['duration_seconds']}")
        print(f"  Haptic experience: {summary['haptic_experience']}")
        print(f"  Checkbox interactions: {summary['checkbox_interactions']}")
        print(f"  Changed mind: {summary['changed_mind']} ({summary['change_count']} changes)")
        print(f"  Changes by checkbox: {summary['changes_by_checkbox']}")
        print(f"  Final selection: {summary['final_summary']}")


def write_plots(summaries: list[dict]) -> None:
    if not summaries:
        return
    df = pd.DataFrame(summaries)
    df["group"] = df["haptic_experience"].map({True: "Haptic", False: "No haptics"})
    df["all_declined"] = (
        (df["final_reject_ads"] == "declined")
        & (df["final_reject_analytics"] == "declined")
        & (df["final_reject_sharing"] == "declined")
    )
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0.0)
    df["change_count"] = pd.to_numeric(df["change_count"], errors="coerce").fillna(0.0)

    changed_mind = df.groupby(["group", "changed_mind"]).size().unstack(fill_value=0)
    outcome = df.groupby(["group", "all_declined"]).size().unstack(fill_value=0)
    duration = df.groupby("group")["duration_seconds"].mean()

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    changed_mind.plot(kind="bar", stacked=False, ax=axes[0])
    axes[0].set_title("Changed mind count by condition")
    axes[0].set_xlabel("Condition")
    axes[0].set_ylabel("Number of sessions")
    axes[0].legend(title="Changed mind")

    outcome.plot(kind="bar", stacked=True, ax=axes[1])
    axes[1].set_title("All declined final choice by condition")
    axes[1].set_xlabel("Condition")
    axes[1].set_ylabel("Number of sessions")
    axes[1].legend(title="All declined")

    duration.plot(kind="bar", ax=axes[2], color=["#4c72b0", "#dd8452"])
    axes[2].set_title("Average session duration by condition")
    axes[2].set_xlabel("Condition")
    axes[2].set_ylabel("Duration (seconds)")

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close(fig)


def print_grouped_summary(summaries: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for summary in summaries:
        key = "experienced" if summary["haptic_experience"] else "not_experienced"
        groups.setdefault(key, []).append(summary)

    print("\nGrouped summary by haptic experience:")
    for key, group in groups.items():
        count = len(group)
        avg_duration = sum(float(s["duration_seconds"] or 0) for s in group) / count
        changed_count = sum(1 for s in group if s["changed_mind"])
        avg_changes = sum(float(s["change_count"] or 0) for s in group) / count
        final_all_declined = sum(
            1 for s in group if s["final_reject_ads"] == "declined" and s["final_reject_analytics"] == "declined" and s["final_reject_sharing"] == "declined"
        )
        print("-" * 60)
        label = "Haptic experienced" if key == "experienced" else "No haptics"
        print(f"{label} sessions: {count}")
        print(f"  Average duration (s): {avg_duration:.3f}")
        print(f"  Sessions with changed mind: {changed_count}/{count}")
        print(f"  Average change count: {avg_changes:.2f}")
        print(f"  All declined final selection: {final_all_declined}/{count}")


def main() -> None:
    events = read_sessions()
    if not events:
        raise SystemExit("No consent behaviour CSVs found in the output folder.")
    write_combined(events)
    session_groups: dict[str, list[Event]] = {}
    for event in events:
        session_groups.setdefault(event.session_id, []).append(event)
    summaries = [session_summary(group) for group in session_groups.values()]
    write_summary(summaries)
    write_grouped_summary(summaries)
    write_plots(summaries)
    print_summary(summaries)
    print_grouped_summary(summaries)
    print(f"Visual analysis written to: {PLOT_FILE}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Evaluate pipeline promotion controls and generate auditable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REQUIRED_FIELDS = {
    "release_id",
    "commit_sha",
    "schema_version",
    "artifact_digest",
    "staged_artifact_digest",
    "controls",
    "environment_evidence",
}


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and minimally validate a release manifest."""
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)

    missing = sorted(REQUIRED_FIELDS - manifest.keys())
    if missing:
        raise ValueError(f"Manifest missing required fields: {', '.join(missing)}")
    if not isinstance(manifest["controls"], dict) or not manifest["controls"]:
        raise ValueError("Manifest controls must be a non-empty object")
    if any(not isinstance(value, bool) for value in manifest["controls"].values()):
        raise ValueError("Every control value must be true or false")
    return manifest


def evaluate(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return an evidence report; every required control must pass."""
    controls = dict(manifest["controls"])
    digest_matches = manifest["artifact_digest"] == manifest["staged_artifact_digest"]
    controls["artifact_digest_match"] = controls.get("artifact_digest_match", False) and digest_matches

    failed = sorted(name for name, passed in controls.items() if not passed)
    return {
        "release_id": manifest["release_id"],
        "commit_sha": manifest["commit_sha"],
        "schema_version": manifest["schema_version"],
        "artifact_digest": manifest["artifact_digest"],
        "decision": "promote" if not failed else "block",
        "required_controls_passed": sum(controls.values()),
        "required_controls_total": len(controls),
        "failed_controls": failed,
        "controls": controls,
        "environment_evidence": manifest["environment_evidence"],
    }


def plot_readiness(report: dict[str, Any], output: Path) -> None:
    """Plot the share of required evidence accumulated per environment."""
    environments = report["environment_evidence"]
    controls = report["controls"]
    labels = list(environments)
    totals = [len(environments[label]) for label in labels]
    passed = [sum(bool(controls.get(name, False)) for name in environments[label]) for label in labels]
    percentages = [100 * ok / total if total else 0 for ok, total in zip(passed, totals)]

    colors = ["#9ecae1", "#6baed6", "#3182bd", "#08519c"]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    bars = ax.bar(labels, percentages, color=colors, width=0.65)
    ax.axhline(100, color="#2b2b2b", linewidth=1, linestyle="--")
    ax.set_ylim(0, 112)
    ax.set_ylabel("Required evidence passed (%)")
    ax.set_xlabel("Pipeline environment")
    ax.set_title(f"Release {report['release_id']}: promotion readiness")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)

    for bar, percent, ok, total in zip(bars, percentages, passed, totals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{ok}/{total}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    decision_color = "#137333" if report["decision"] == "promote" else "#b3261e"
    ax.text(
        0.99,
        0.08,
        f"Decision: {report['decision'].upper()}",
        transform=ax.transAxes,
        ha="right",
        color=decision_color,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": decision_color},
    )
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    report = evaluate(manifest)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_readiness(report, args.figure)

    print(
        f"{report['release_id']}: {report['required_controls_passed']}/"
        f"{report['required_controls_total']} controls passed; "
        f"decision={report['decision']}"
    )
    if report["failed_controls"]:
        print("Failed controls: " + ", ".join(report["failed_controls"]))
    return 0 if report["decision"] == "promote" else 1


if __name__ == "__main__":
    raise SystemExit(main())

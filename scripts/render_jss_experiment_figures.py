from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from common import ensure_dir, repo_path


MPL_CONFIG_DIR = repo_path("artifacts", ".matplotlib")
XDG_CACHE_DIR = repo_path("artifacts", ".cache")
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
XDG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(XDG_CACHE_DIR))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402


FIG_DIR = repo_path("paper", "jss_dsc_guard", "figures")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save(fig: plt.Figure, name: str) -> None:
    ensure_dir(FIG_DIR)
    fig.savefig(FIG_DIR / name, bbox_inches="tight")
    plt.close(fig)


def style() -> None:
    plt.rcParams.update(
        {
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "legend.fontsize": 6,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#444444",
            "axes.linewidth": 0.6,
        }
    )


def fmt_int(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{int(value)}"


def render_intro_trend() -> None:
    rows = read_csv_rows(repo_path("artifacts", "broad_search", "oracle_scope_cumulative_trend", "result.csv"))
    series = [
        row
        for row in rows
        if row["chain"] == "all_active_case_chains"
        and row.get("cumulative_oracle_log_count")
        and row.get("month")
    ]
    series.sort(key=lambda row: row["month"])
    months = [datetime.strptime(row["month"], "%Y-%m-%d") for row in series]
    logs_m = [int(row["cumulative_oracle_log_count"]) / 1_000_000 for row in series]

    fig, ax = plt.subplots(figsize=(3.35, 2.05))
    ax.plot(months, logs_m, color="#1f4e79", linewidth=1.7)
    ax.fill_between(months, logs_m, color="#9ecae1", alpha=0.25)
    ax.set_ylabel("Cumulative logs (M)")
    ax.set_xlabel("Month")
    ax.grid(True, axis="y", color="#dddddd", linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if months:
        final_value = int(series[-1]["cumulative_oracle_log_count"])
        ax.annotate(
            fmt_int(final_value),
            xy=(months[-1], logs_m[-1]),
            xytext=(-31, -3),
            textcoords="offset points",
            fontsize=7,
            color="#1f4e79",
            arrowprops={"arrowstyle": "-", "color": "#1f4e79", "linewidth": 0.6},
        )
    fig.autofmt_xdate(rotation=25, ha="right")
    save(fig, "intro_oracle_scope_trend.pdf")


def render_dataset_funnel() -> None:
    cumulative_rows = read_csv_rows(
        repo_path("artifacts", "broad_search", "oracle_scope_cumulative_trend", "result.csv")
    )
    all_rows = [row for row in cumulative_rows if row["chain"] == "all_active_case_chains"]
    all_rows.sort(key=lambda row: row["month"])
    broad_logs = int(all_rows[-1]["cumulative_oracle_log_count"])

    rq2 = read_json(repo_path("artifacts", "evaluation", "rq2_log_level_metrics.json"))
    benign = rq2["benign"]
    positive = rq2["positive"]

    labels = [
        "Remote oracle-scope logs",
        "Local replay rows",
        "Labelled benign rows",
        "Unknown excluded rows",
        "Positive semantic logs",
        "Incident warnings",
    ]
    labelled_benign = benign["strict_benign_log_rows"] + benign["review_or_alert_log_rows_excluded"]
    values = [
        broad_logs,
        benign["materialized_log_rows"] + positive["all_semantic_log_records"],
        labelled_benign,
        benign["unknown_log_rows_excluded"],
        positive["all_semantic_log_records"],
        positive["detected_target_log_records"],
    ]
    colors = ["#4d4d4d", "#6baed6", "#74c476", "#bdbdbd", "#fd8d3c", "#e6550d"]

    fig, ax = plt.subplots(figsize=(3.35, 2.35))
    y = list(range(len(labels)))
    ax.barh(y, values, color=colors, height=0.58)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Rows / logs (log scale)")
    ax.grid(True, axis="x", color="#dddddd", linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for ypos, value in zip(y, values):
        ax.text(value * 1.12, ypos, fmt_int(value), va="center", fontsize=6)
    save(fig, "eval_dataset_funnel.pdf")


def case_label(case: str) -> str:
    return {
        "ploutos": "Ploutos",
        "moonwell_cbeth": "MW cbETH",
        "moonwell_wrseth": "MW wrsETH",
        "blueberry_faulty_oracle": "Blueberry",
        "venus_luna": "Venus",
        "blizz_luna": "Blizz",
    }.get(case, case)


def render_log_warning_breakdown() -> None:
    rq2 = read_json(repo_path("artifacts", "evaluation", "rq2_log_level_metrics.json"))
    cases = rq2["positive"]["per_case"]

    labels = [case_label(row["case"]) for row in cases]
    direct = [row["direct_violation_target_log_records"] for row in cases]
    early = [row["early_evidence_target_log_records"] for row in cases]
    support = [row["support_only_context_records"] for row in cases]
    recalls = [row["target_log_records"] / row["all_trace_records"] for row in cases]

    fig, ax = plt.subplots(figsize=(3.35, 2.45))
    y = list(range(len(labels)))
    ax.barh(y, direct, color="#3182bd", label="Direct violation")
    ax.barh(y, early, left=direct, color="#fd8d3c", label="Early evidence")
    left_support = [d + e for d, e in zip(direct, early)]
    ax.barh(y, support, left=left_support, color="#bdbdbd", label="Support context")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Semantic log records")
    ax.grid(True, axis="x", color="#dddddd", linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for ypos, total, recall in zip(y, [d + e + s for d, e, s in zip(direct, early, support)], recalls):
        ax.text(total + max(1.5, total * 0.015), ypos, f"{recall * 100:.1f}%", va="center", fontsize=6)
    ax.legend(loc="lower right", frameon=False, ncol=1)
    save(fig, "eval_log_warning_breakdown.pdf")


def render_ablation_heatmap() -> None:
    data = read_json(repo_path("artifacts", "evaluation", "rq2_ablation_study.json"))
    variants = data["variants"]
    order = [
        "full_dsc_guard",
        "without_log_semantics_abi_only",
        "topic_only_raw_filter",
        "oracle_boundary_without_lending_binding",
        "impact_only_without_oracle_boundary",
    ]
    by_variant = {row["variant"]: row for row in variants}
    rows = [by_variant[name] for name in order if name in by_variant]
    row_labels = {
        "full_dsc_guard": "Full",
        "without_log_semantics_abi_only": "ABI-only",
        "topic_only_raw_filter": "Topic-only",
        "oracle_boundary_without_lending_binding": "Oracle-only",
        "impact_only_without_oracle_boundary": "Impact-only",
    }
    metrics = [
        ("Replayable\ncase recall", "replayable_case_recall"),
        ("Impact tx\nrecall", "impact_tx_recall"),
        ("Actor\nrecall", "actor_recall"),
        ("Benign\nwarning rate", "benign_warning_rate"),
    ]
    matrix = [[row[key] for _, key in metrics] for row in rows]

    cmap = LinearSegmentedColormap.from_list("dsc_guard_heat", ["#f7fbff", "#6baed6", "#08306b"])
    fig, ax = plt.subplots(figsize=(3.35, 2.25))
    im = ax.imshow(matrix, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels([name for name, _ in metrics])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([row_labels[row["variant"]] for row in rows])
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            text_color = "white" if value > 0.62 else "#222222"
            ax.text(j, i, f"{value * 100:.1f}%", ha="center", va="center", fontsize=6, color=text_color)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    cbar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cbar.ax.set_ylabel("Rate", rotation=270, labelpad=8)
    save(fig, "eval_ablation_heatmap.pdf")


def main() -> None:
    style()
    ensure_dir(MPL_CONFIG_DIR)
    render_intro_trend()
    render_dataset_funnel()
    render_log_warning_breakdown()
    render_ablation_heatmap()
    for name in (
        "intro_oracle_scope_trend.pdf",
        "eval_dataset_funnel.pdf",
        "eval_log_warning_breakdown.pdf",
        "eval_ablation_heatmap.pdf",
    ):
        print(FIG_DIR / name)


if __name__ == "__main__":
    main()

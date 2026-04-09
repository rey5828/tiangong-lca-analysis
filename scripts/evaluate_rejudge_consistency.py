import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path


SAMPLE_DIR = Path("output/agent_results/stratified_samples")
RESULTS_DIR = Path("output/agent_results/verified_stratified_samples/results")
DEFAULT_OUTPUT_PATH = Path("output/agent_results/verified_stratified_samples/rejudge_consistency_report.md")
LABELS = ["Negative", "Neutral", "Positive"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate consistency between sampled qualitative_relationship and verified re-judgment results.")
    parser.add_argument("--sample-dir", default=str(SAMPLE_DIR), help="Directory of original stratified sample JSON files.")
    parser.add_argument("--results-dir", default=str(RESULTS_DIR), help="Directory of verified result folders.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Markdown report output path.")
    parser.add_argument("--bootstrap-runs", type=int, default=50, help="Number of bootstrap resamples.")
    parser.add_argument("--seed-base", type=int, default=0, help="Starting seed for bootstrap resamples.")
    return parser.parse_args()


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def record_key(process_id: str, flow_combo: str, ghg_combo: str) -> tuple[str, str, str]:
    return (
        normalize_text(process_id),
        normalize_text(flow_combo),
        normalize_text(ghg_combo),
    )


def find_result_dir(results_dir: Path, sample_stem: str) -> Path | None:
    candidates = sorted([path for path in results_dir.iterdir() if path.is_dir() and path.name.startswith(sample_stem + "_")])
    if not candidates:
        return None
    return candidates[-1]


def build_truth_index(summary_path: Path) -> dict[tuple[str, str, str], dict]:
    summary = load_json(summary_path)
    truth_index = {}

    for result in summary.get("results", []):
        llm_result = result.get("llm_result") or {}
        for flow_analysis in llm_result.get("flow_analyses", []):
            process_id = flow_analysis.get("process_id") or result.get("process_id")
            flow_combo = flow_analysis.get("flow_combo") or result.get("flow_combo")
            for analysis in flow_analysis.get("individual_ghg_analyses", []):
                key = record_key(process_id, flow_combo, analysis.get("ghg_combo"))
                truth_index[key] = {
                    "qualitative_relationship": analysis.get("qualitative_relationship"),
                    "mechanism_archetype": analysis.get("mechanism_archetype"),
                    "evidence_sufficiency": analysis.get("evidence_sufficiency"),
                    "risk_score": analysis.get("risk_score"),
                }

    return truth_index


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_sample(pairs: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    return [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]


def accuracy_from_pairs(pairs: list[tuple[str, str]]) -> float:
    return sum(1 for pred, truth in pairs if pred == truth) / len(pairs)


def precision_recall_f1(pairs: list[tuple[str, str]], labels: list[str]) -> dict[str, float]:
    per_label_precision = []
    per_label_recall = []
    per_label_f1 = []

    for label in labels:
        tp = sum(1 for pred, truth in pairs if pred == label and truth == label)
        fp = sum(1 for pred, truth in pairs if pred == label and truth != label)
        fn = sum(1 for pred, truth in pairs if pred != label and truth == label)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        per_label_precision.append(precision)
        per_label_recall.append(recall)
        per_label_f1.append(f1)

    return {
        "macro_precision": sum(per_label_precision) / len(labels),
        "macro_recall": sum(per_label_recall) / len(labels),
        "macro_f1": sum(per_label_f1) / len(labels),
    }


def summarize_metric(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "mean": mean,
        "std": math.sqrt(variance),
        "min": min(values),
        "q05": percentile(values, 0.05),
        "q25": percentile(values, 0.25),
        "median": percentile(values, 0.50),
        "q75": percentile(values, 0.75),
        "q95": percentile(values, 0.95),
        "max": max(values),
    }


def bootstrap_accuracy_stats(pairs: list[tuple[str, str]], bootstrap_runs: int, seed_base: int) -> dict[str, dict[str, float]]:
    accuracy_values = []
    error_values = []

    for offset in range(bootstrap_runs):
        rng = random.Random(seed_base + offset)
        sampled_pairs = bootstrap_sample(pairs, rng)
        accuracy = accuracy_from_pairs(sampled_pairs)
        accuracy_values.append(accuracy)
        error_values.append(1.0 - accuracy)

    return {
        "accuracy": summarize_metric(accuracy_values),
        "error_rate": summarize_metric(error_values),
    }


def bootstrap_overall_multiclass_stats(pairs: list[tuple[str, str]], bootstrap_runs: int, seed_base: int) -> dict[str, dict[str, float]]:
    metrics = {
        "accuracy": [],
        "error_rate": [],
        "macro_precision": [],
        "macro_recall": [],
        "macro_f1": [],
    }

    for offset in range(bootstrap_runs):
        rng = random.Random(seed_base + offset)
        sampled_pairs = bootstrap_sample(pairs, rng)
        accuracy = accuracy_from_pairs(sampled_pairs)
        metrics["accuracy"].append(accuracy)
        metrics["error_rate"].append(1.0 - accuracy)
        prf = precision_recall_f1(sampled_pairs, LABELS)
        for key, value in prf.items():
            metrics[key].append(value)

    return {metric_name: summarize_metric(values) for metric_name, values in metrics.items()}


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_bootstrap_summary(metric_summary: dict[str, float]) -> str:
    return (
        f"mean {format_pct(metric_summary['mean'])}, "
        f"std {format_pct(metric_summary['std'])}, "
        f"p05 {format_pct(metric_summary['q05'])}, "
        f"median {format_pct(metric_summary['median'])}, "
        f"p95 {format_pct(metric_summary['q95'])}"
    )


def render_markdown(
    layer_reports: list[dict],
    overall_report: dict,
    bootstrap_runs: int,
    seed_base: int,
    sample_dir: Path,
    results_dir: Path,
) -> str:
    lines = []
    lines.append("# Blind Rejudge Consistency Report")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Sample directory: `{sample_dir}`")
    lines.append(f"- Verified results directory: `{results_dir}`")
    lines.append(f"- Bootstrap runs per evaluation: `{bootstrap_runs}`")
    lines.append(f"- Bootstrap seed range: `{seed_base}` to `{seed_base + bootstrap_runs - 1}`")
    lines.append("- Matching key: `process_id + flow_combo + ghg_combo`")
    lines.append("- Ground truth assumption: `summary.json` in each verified folder is treated as correct.")
    lines.append("")
    lines.append("## Method Notes")
    lines.append("")
    lines.append("- Accuracy and error rate are computed on matched objects only.")
    lines.append("- Coverage is reported separately as matched vs. unmatched counts.")
    lines.append("- Per-layer Precision / Recall / F1 are intentionally omitted because each stratified layer contains a single original predicted relationship class by construction, so per-layer P/R/F1 would be degenerate and less informative than accuracy.")
    lines.append("- To keep a multiclass view, overall macro Precision / Recall / F1 are reported across all matched objects from all layers.")
    lines.append("")
    lines.append("## Layer Summary")
    lines.append("")
    lines.append("| Layer | Result Folder | Total Objects | Matched | Unmatched | Coverage | Point Accuracy | Point Error | Bootstrap Accuracy | Bootstrap Error | Original Relationship Mix | Verified Relationship Mix |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |")

    for report in layer_reports:
        lines.append(
            "| {layer} | `{result_dir}` | {total} | {matched} | {unmatched} | {coverage} | {accuracy} | {error} | {boot_acc} | {boot_err} | `{pred_mix}` | `{truth_mix}` |".format(
                layer=report["layer_name"],
                result_dir=report["result_dir_name"] or "missing",
                total=report["total_objects"],
                matched=report["matched_objects"],
                unmatched=report["unmatched_objects"],
                coverage=format_pct(report["coverage"]),
                accuracy=format_pct(report["point_accuracy"]) if report["matched_objects"] else "n/a",
                error=format_pct(report["point_error"]) if report["matched_objects"] else "n/a",
                boot_acc=format_bootstrap_summary(report["bootstrap"]["accuracy"]) if report["matched_objects"] else "n/a",
                boot_err=format_bootstrap_summary(report["bootstrap"]["error_rate"]) if report["matched_objects"] else "n/a",
                pred_mix=", ".join(f"{key}:{value}" for key, value in sorted(report["pred_counts"].items())),
                truth_mix=", ".join(f"{key}:{value}" for key, value in sorted(report["truth_counts"].items())),
            )
        )

    lines.append("")
    lines.append("## Overall Matched Evaluation")
    lines.append("")
    lines.append(f"- Total matched objects across all layers: `{overall_report['matched_objects']}`")
    lines.append(f"- Total unmatched objects across all layers: `{overall_report['unmatched_objects']}`")
    lines.append(f"- Coverage across all layers: `{format_pct(overall_report['coverage'])}`")
    lines.append(f"- Point accuracy: `{format_pct(overall_report['point_accuracy'])}`")
    lines.append(f"- Point error rate: `{format_pct(overall_report['point_error'])}`")
    lines.append(f"- Point macro precision: `{format_pct(overall_report['point_macro_precision'])}`")
    lines.append(f"- Point macro recall: `{format_pct(overall_report['point_macro_recall'])}`")
    lines.append(f"- Point macro F1: `{format_pct(overall_report['point_macro_f1'])}`")
    lines.append("")
    lines.append("### Overall Bootstrap")
    lines.append("")
    for metric_name in ["accuracy", "error_rate", "macro_precision", "macro_recall", "macro_f1"]:
        lines.append(f"- `{metric_name}`: {format_bootstrap_summary(overall_report['bootstrap'][metric_name])}")

    lines.append("")
    lines.append("### Overall Confusion Matrix")
    lines.append("")
    lines.append("| Original \\ Verified | Negative | Neutral | Positive |")
    lines.append("| --- | ---: | ---: | ---: |")
    confusion = overall_report["confusion_matrix"]
    for pred_label in LABELS:
        lines.append(
            f"| {pred_label} | {confusion[pred_label]['Negative']} | {confusion[pred_label]['Neutral']} | {confusion[pred_label]['Positive']} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    sample_dir = Path(args.sample_dir)
    results_dir = Path(args.results_dir)
    output_path = Path(args.output)

    layer_reports = []
    overall_pairs = []
    total_objects_all = 0
    matched_objects_all = 0

    for sample_path in sorted(sample_dir.glob("*.json")):
        sample_name = sample_path.stem
        result_dir = find_result_dir(results_dir, sample_name)
        summary_path = result_dir / "summary.json" if result_dir else None

        sample_records = load_json(sample_path)
        truth_index = build_truth_index(summary_path) if summary_path and summary_path.exists() else {}

        matched_pairs = []
        unmatched_count = 0
        pred_counts = Counter()
        truth_counts = Counter()

        for record in sample_records:
            pred_label = record.get("qualitative_relationship")
            pred_counts[pred_label] += 1
            key = record_key(record.get("process_id"), record.get("flow_combo"), record.get("ghg_combo"))
            truth = truth_index.get(key)
            if truth is None:
                unmatched_count += 1
                continue

            truth_label = truth.get("qualitative_relationship")
            truth_counts[truth_label] += 1
            matched_pairs.append((pred_label, truth_label))

        total_objects = len(sample_records)
        matched_objects = len(matched_pairs)
        total_objects_all += total_objects
        matched_objects_all += matched_objects
        overall_pairs.extend(matched_pairs)

        layer_report = {
            "layer_name": sample_name,
            "result_dir_name": result_dir.name if result_dir else None,
            "total_objects": total_objects,
            "matched_objects": matched_objects,
            "unmatched_objects": unmatched_count,
            "coverage": matched_objects / total_objects if total_objects else 0.0,
            "pred_counts": dict(pred_counts),
            "truth_counts": dict(truth_counts),
        }

        if matched_objects:
            point_accuracy = accuracy_from_pairs(matched_pairs)
            layer_report["point_accuracy"] = point_accuracy
            layer_report["point_error"] = 1.0 - point_accuracy
            layer_report["bootstrap"] = bootstrap_accuracy_stats(matched_pairs, args.bootstrap_runs, args.seed_base)
        else:
            layer_report["point_accuracy"] = 0.0
            layer_report["point_error"] = 0.0
            layer_report["bootstrap"] = {}

        layer_reports.append(layer_report)

    if not overall_pairs:
        raise SystemExit("No matched records found between samples and verified summaries.")

    overall_accuracy = accuracy_from_pairs(overall_pairs)
    overall_prf = precision_recall_f1(overall_pairs, LABELS)
    confusion = {pred: {truth: 0 for truth in LABELS} for pred in LABELS}
    for pred, truth in overall_pairs:
        confusion[pred][truth] += 1

    overall_report = {
        "matched_objects": matched_objects_all,
        "unmatched_objects": total_objects_all - matched_objects_all,
        "coverage": matched_objects_all / total_objects_all if total_objects_all else 0.0,
        "point_accuracy": overall_accuracy,
        "point_error": 1.0 - overall_accuracy,
        "point_macro_precision": overall_prf["macro_precision"],
        "point_macro_recall": overall_prf["macro_recall"],
        "point_macro_f1": overall_prf["macro_f1"],
        "bootstrap": bootstrap_overall_multiclass_stats(overall_pairs, args.bootstrap_runs, args.seed_base),
        "confusion_matrix": confusion,
    }

    markdown = render_markdown(
        layer_reports=layer_reports,
        overall_report=overall_report,
        bootstrap_runs=args.bootstrap_runs,
        seed_base=args.seed_base,
        sample_dir=sample_dir,
        results_dir=results_dir,
    )
    dump_text(output_path, markdown)
    print(f"Saved report to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Choose Coreograph's downsample factor for one slide from the sweep's metrics.

Score = count_error + diam_error + size_cv; lowest wins, ties go to the smaller k. A poor
winner only warns; a sweep in which no factor found any core stops the run, since COREOGRAPH
would then fail later and less clearly.
"""

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

COLUMNS = [
    "k", "um_per_px", "n_cores", "count_error", "diam_mm", "diam_error", "size_cv",
    "crop_ratio", "core_px_at_k", "score", "selected", "warning",
]  # fmt: skip
MAX_COUNT_ERROR = 0.1
MAX_DIAM_ERROR = 0.25


def score(m: dict) -> float:
    if not m["n_cores"]:
        return math.inf
    return m["count_error"] + m["diam_error"] + m["size_cv"]


def choose(metrics: list[dict]) -> dict:
    return min(metrics, key=lambda m: (score(m), m["k"]))


def warning(m: dict) -> str | None:
    if m["count_error"] <= MAX_COUNT_ERROR and (m["diam_error"] or 0) <= MAX_DIAM_ERROR:
        return None
    diam = f"{m['diam_mm']:.2f} mm" if m.get("diam_mm") is not None else "no"
    return (
        f"best downsample factor k={m['k']} still finds {m['n_cores']} cores "
        f"(count off by {m['count_error']:.0%}) with {diam} median diameter "
        f"(off by {(m['diam_error'] or 0):.0%}); check the sweep overlays before trusting the cores"
    )


def write_panel(path: Path, overlays: list[Path]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def k_of(p: Path) -> int:
        match = re.search(r"_k(\d+)_overlay\.png$", p.name)
        return int(match.group(1)) if match else 0

    overlays = sorted(overlays, key=k_of)
    fig, axes = plt.subplots(1, len(overlays), figsize=(5 * len(overlays), 5.4), squeeze=False)
    for ax, p in zip(axes[0], overlays, strict=True):
        ax.imshow(plt.imread(p))
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metrics", type=Path, nargs="+", required=True)
    parser.add_argument("--overlays", type=Path, nargs="+", required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args(argv)

    metrics = [json.loads(p.read_text()) for p in args.metrics]
    best = choose(metrics)
    if score(best) == math.inf:
        sys.exit(
            f"{args.prefix}: no downsample factor detected any core. Check that the dearray channel "
            "(--channel, default 0) is a nuclear stain, or set coreograph_args to run Coreograph yourself."
        )
    note = warning(best)
    if note:
        print(f"WARNING {args.prefix}: {note}", file=sys.stderr)

    with Path(f"{args.prefix}_sweep.tsv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for m in sorted(metrics, key=lambda m: (score(m), m["k"])):
            chosen = m is best
            row = {**m, "score": score(m), "selected": str(chosen).lower(), "warning": note if chosen else ""}
            # 4 decimals: pixel sizes come from float32 OME metadata and print as 20.799999237.
            writer.writerow({c: round(v, 4) if isinstance(v, float) else v for c, v in row.items()})
    Path(f"{args.prefix}_selection.json").write_text(
        json.dumps({"downsample_factor": best["k"], "warning": note}) + "\n"
    )
    write_panel(Path(f"{args.prefix}_sweep_overlays.png"), args.overlays)


if __name__ == "__main__":
    main()

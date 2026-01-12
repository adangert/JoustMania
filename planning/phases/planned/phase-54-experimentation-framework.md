# Phase 54: Experimentation Framework & Tools

**Status**: 📋 PLANNED
**Priority**: Medium
**Estimated Effort**: 1 week
**Dependencies**: Phase 49 (Profiles), Phase 51 (Flagd), Phase 52 (Flag Adjustments), Phase 53 (Web UI)
**Blocks**: None (enables systematic testing)

---

## Overview

Build automation tools and analysis scripts to systematically run experiments comparing different runtime configurations. Enable data-driven decision making for demo configurations and gameplay tuning.

**Goals:**
- Create experiment runner script for automated execution
- Build statistical analysis tools (t-tests, effect size, confidence intervals)
- Design experiment template and documentation framework
- Integrate with Prometheus/Grafana for metrics collection
- Generate comparison reports with visualizations
- Export results to CSV for external analysis

---

## Why This Phase Matters

**Current limitation:** Testing different configurations requires:
- Manual game execution
- Manual metrics collection
- Manual comparison of results
- No statistical significance testing
- No documentation of experiment parameters or outcomes

**After this phase:**
- Automated experiment execution (N rounds per treatment group)
- Statistical analysis with p-values and effect sizes
- Structured experiment documentation
- Reproducible results
- Data-driven insights for demos and configuration tuning

---

## Architecture

### Experiment Workflow

```
┌────────────────────────────────────────────────────────────┐
│  1. Define Experiment (experiment_template.md)            │
│     - Hypothesis                                            │
│     - Variables (control vs treatment)                     │
│     - Success metrics                                      │
│     - Sample size                                          │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│  2. Configure Flags (Web UI)                               │
│     - Set control group flags                              │
│     - Set treatment group flags                            │
│     - Enable percentage rollout or manual assignment       │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│  3. Run Experiment (experiment_runner.py)                  │
│     - Execute N rounds for each group                      │
│     - Assign groups (round-robin, random, percentage)      │
│     - Collect metrics from Prometheus                      │
│     - Export raw data to CSV                               │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│  4. Analyze Results (analyze_experiment.py)                │
│     - Load experiment data                                 │
│     - Compute descriptive statistics                       │
│     - Run statistical tests (t-tests, Mann-Whitney)        │
│     - Calculate effect sizes (Cohen's d)                   │
│     - Generate comparison visualizations                   │
│     - Create experiment report (markdown)                  │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│  5. Review & Decide                                        │
│     - Read experiment report                               │
│     - Review statistical significance                      │
│     - Make configuration decision                          │
│     - Update default flags if conclusive                   │
└────────────────────────────────────────────────────────────┘
```

---

## Experiment Template

**File**: `experiments/templates/experiment_template.md`

```markdown
# Experiment: [Short Descriptive Name]

**Experiment ID**: `exp_[YYYYMMDD]_[short_name]`
**Date**: YYYY-MM-DD
**Status**: 🔵 PLANNED / 🟢 RUNNING / ✅ COMPLETED / ❌ CANCELLED
**Owner**: [Your Name]

---

## Hypothesis

**What we're testing:**
[Clear statement of what you expect to happen]

Example: "Bidirectional streaming reduces input-to-feedback latency by >15% compared to unary RPCs, with <10% CPU overhead increase."

---

## Variables

### Independent Variable (What we're changing)

**Variable**: `streaming_mode`
**Control Group**: `unary_fallback`
**Treatment Group(s)**: `bidirectional`

### Dependent Variables (What we're measuring)

1. **Primary metric**: `game_loop_latency_p95` (ms)
   - Expected direction: Decrease
   - Minimum detectable effect: 15% reduction

2. **Secondary metrics**:
   - `cpu_usage_percent` (%)
   - `network_bytes_sent_per_second` (bytes/s)
   - `controller_feedback_delay_p95` (ms)

---

## Experimental Design

**Type**: A/B Test (two groups)
**Assignment**: Round-robin (alternating control/treatment per game)
**Sample Size**: 30 games per group (60 total)
**Game Mode**: FFA
**Controller Count**: 25
**Duration**: Estimated 2 hours

**Randomization**: Manual round-robin assignment to avoid confounds from game order

**Exclusion Criteria**:
- Games with <20 controllers (insufficient load)
- Games with controller disconnections >3
- Games lasting <60 seconds (anomalous)

---

## Flag Configuration

### Control Group Flags
```json
{
  "streaming_mode": "unary_fallback",
  "enable_dynamic_filtering": false
}
```

### Treatment Group Flags
```json
{
  "streaming_mode": "bidirectional",
  "enable_dynamic_filtering": true
}
```

---

## Success Criteria

**Primary goal**: Reduce latency by ≥15% with <10% CPU increase

**Decision matrix**:
- ✅ **Adopt treatment**: Latency ↓≥15%, CPU ↑<10%, p<0.05
- ⚠️ **Re-test with modifications**: Latency ↓10-15% OR CPU ↑10-15%
- ❌ **Keep control**: Latency ↓<10% OR CPU ↑>15%

---

## Results

### Data Collection

**Completed**: [Date]
**Games executed**: Control: 30, Treatment: 30
**Exclusions**: 2 games (controller disconnections)
**Final sample**: Control: 29, Treatment: 29

### Statistical Analysis

**Latency (ms):**
- Control: 30.2 ± 4.1 (mean ± SD)
- Treatment: 22.1 ± 3.2
- Difference: -27% (8.1ms reduction)
- t-test: t=-8.42, p=0.001 (significant)
- Effect size: Cohen's d = 2.19 (very large)

**CPU Usage (%):**
- Control: 22.1 ± 2.3
- Treatment: 23.8 ± 2.1
- Difference: +7.7% (1.7% increase)
- t-test: t=2.94, p=0.005 (significant but small)
- Effect size: Cohen's d = 0.77 (medium)

**Bandwidth (KB/s):**
- Control: 22.4 ± 1.2
- Treatment: 23.1 ± 1.5
- Difference: +3.1%
- t-test: t=1.98, p=0.052 (not significant)

### Visualizations

[Charts generated by analyze_experiment.py]

---

## Interpretation

**Summary**: Bidirectional streaming significantly reduces latency (-27%) with acceptable CPU overhead (+7.7%). Effect is larger than hypothesized (15% target).

**Confidence**: High (p<0.001, very large effect size)

**Recommendation**: ✅ **Adopt bidirectional streaming as default**

**Trade-offs**: Slight CPU increase is acceptable given substantial latency improvement. Bandwidth unchanged.

---

## Next Steps

- [ ] Update default `streaming_mode` flag to `bidirectional`
- [ ] Monitor production for 1 week
- [ ] Document in system architecture
- [ ] Consider follow-up experiment: Hybrid mode for high controller counts

---

**End of Experiment**
```

---

## Implementation: Experiment Runner

**File**: `tools/experiment_runner.py`

```python
#!/usr/bin/env python3
"""
Experiment runner for automated testing of runtime configurations.

Usage:
    python tools/experiment_runner.py \\
        --experiment-id exp_20260112_streaming_comparison \\
        --control-flags '{"streaming_mode": "unary_fallback"}' \\
        --treatment-flags '{"streaming_mode": "bidirectional"}' \\
        --rounds-per-group 30 \\
        --game-mode FFA \\
        --controller-count 25
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
from prometheus_api_client import PrometheusConnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Runs automated experiments with multiple treatment groups."""

    def __init__(
        self,
        experiment_id: str,
        prometheus_url: str = "http://localhost:9090",
        web_ui_url: str = "http://localhost:8080",
        output_dir: str = "experiments/data"
    ):
        self.experiment_id = experiment_id
        self.prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)
        self.web_ui_url = web_ui_url
        self.output_dir = Path(output_dir) / experiment_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def set_flags(self, flags: Dict[str, any]) -> None:
        """Update flags via Web UI API."""

        logger.info(f"Setting flags: {flags}")

        for flag_key, value in flags.items():
            response = requests.post(
                f"{self.web_ui_url}/api/flags/update",
                json={"flag_key": flag_key, "value": value}
            )

            if response.status_code != 200:
                raise RuntimeError(f"Failed to set flag {flag_key}: {response.text}")

        # Wait for flagd to sync
        logger.info("Waiting 10s for flagd sync...")
        time.sleep(10)

    def wait_for_game_start(self) -> str:
        """Wait for a game to start and return game_id."""

        logger.info("Waiting for game to start...")

        while True:
            # Poll for active game via Web UI or game coordinator
            response = requests.get(f"{self.web_ui_url}/api/game/current")

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "running":
                    game_id = data["game_id"]
                    logger.info(f"Game started: {game_id}")
                    return game_id

            time.sleep(2)

    def wait_for_game_end(self, game_id: str) -> None:
        """Wait for game to complete."""

        logger.info(f"Waiting for game {game_id} to end...")

        while True:
            response = requests.get(f"{self.web_ui_url}/api/game/current")

            if response.status_code == 200:
                data = response.json()
                if data.get("status") != "running":
                    logger.info(f"Game {game_id} completed")
                    return

            time.sleep(2)

    def collect_metrics(self, game_id: str) -> Dict[str, float]:
        """Collect metrics for completed game from Prometheus."""

        logger.info(f"Collecting metrics for game {game_id}")

        metrics = {}

        # Query Prometheus for game metrics
        queries = {
            "latency_p95": 'histogram_quantile(0.95, rate(game_loop_latency_seconds_bucket[5m]))',
            "latency_mean": 'rate(game_loop_latency_seconds_sum[5m]) / rate(game_loop_latency_seconds_count[5m])',
            "cpu_usage": 'rate(process_cpu_seconds_total[5m]) * 100',
            "memory_mb": 'process_resident_memory_bytes / 1024 / 1024',
            "bandwidth_kbps": 'rate(network_bytes_sent_total[5m]) / 1024',
        }

        for metric_name, query in queries.items():
            result = self.prom.custom_query(query=query)

            if result:
                # Extract value from Prometheus result
                value = float(result[0]['value'][1])
                metrics[metric_name] = value
            else:
                logger.warning(f"No data for metric: {metric_name}")
                metrics[metric_name] = None

        return metrics

    def run_experiment(
        self,
        control_flags: Dict[str, any],
        treatment_flags: Dict[str, any],
        rounds_per_group: int,
        game_mode: str,
        assignment: str = "round_robin"
    ) -> None:
        """
        Run experiment with control and treatment groups.

        Args:
            control_flags: Flags for control group
            treatment_flags: Flags for treatment group
            rounds_per_group: Number of games per group
            game_mode: Game mode to test
            assignment: "round_robin", "random", or "block"
        """

        logger.info(f"Starting experiment: {self.experiment_id}")
        logger.info(f"Rounds per group: {rounds_per_group}")
        logger.info(f"Assignment: {assignment}")

        results = []
        total_rounds = rounds_per_group * 2

        for round_num in range(total_rounds):
            # Determine group assignment
            if assignment == "round_robin":
                is_treatment = (round_num % 2 == 1)
            elif assignment == "block":
                is_treatment = (round_num >= rounds_per_group)
            else:  # random
                import random
                is_treatment = random.random() > 0.5

            group = "treatment" if is_treatment else "control"
            flags = treatment_flags if is_treatment else control_flags

            logger.info(f"\\n--- Round {round_num + 1}/{total_rounds} ({group}) ---")

            # Set flags for this round
            self.set_flags(flags)

            # Wait for game to start (manual start or automated)
            game_id = self.wait_for_game_start()

            # Wait for game to complete
            self.wait_for_game_end(game_id)

            # Collect metrics
            metrics = self.collect_metrics(game_id)

            # Store result
            result = {
                "round": round_num + 1,
                "group": group,
                "game_id": game_id,
                "game_mode": game_mode,
                "timestamp": datetime.now().isoformat(),
                "flags": flags,
                "metrics": metrics
            }

            results.append(result)

            # Save intermediate results
            self._save_results(results)

            logger.info(f"Round {round_num + 1} complete: {metrics}")

        logger.info(f"\\nExperiment complete! Results saved to {self.output_dir}")

    def _save_results(self, results: List[Dict]) -> None:
        """Save results to JSON and CSV."""

        # Save JSON
        json_path = self.output_dir / "results.json"
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2)

        # Save CSV
        csv_path = self.output_dir / "results.csv"
        with open(csv_path, 'w') as f:
            if not results:
                return

            # Header
            metrics_keys = results[0]["metrics"].keys()
            f.write("round,group,game_id,timestamp," + ",".join(metrics_keys) + "\\n")

            # Data
            for r in results:
                metrics_vals = [str(r["metrics"].get(k, "")) for k in metrics_keys]
                f.write(f"{r['round']},{r['group']},{r['game_id']},{r['timestamp']}," + ",".join(metrics_vals) + "\\n")


def main():
    parser = argparse.ArgumentParser(description="Run automated experiment")
    parser.add_argument("--experiment-id", required=True, help="Experiment ID")
    parser.add_argument("--control-flags", required=True, help="Control group flags (JSON)")
    parser.add_argument("--treatment-flags", required=True, help="Treatment group flags (JSON)")
    parser.add_argument("--rounds-per-group", type=int, default=10, help="Games per group")
    parser.add_argument("--game-mode", default="FFA", help="Game mode")
    parser.add_argument("--assignment", default="round_robin", choices=["round_robin", "random", "block"])

    args = parser.parse_args()

    control_flags = json.loads(args.control_flags)
    treatment_flags = json.loads(args.treatment_flags)

    runner = ExperimentRunner(experiment_id=args.experiment_id)
    runner.run_experiment(
        control_flags=control_flags,
        treatment_flags=treatment_flags,
        rounds_per_group=args.rounds_per_group,
        game_mode=args.game_mode,
        assignment=args.assignment
    )


if __name__ == "__main__":
    main()
```

---

## Implementation: Analysis Script

**File**: `tools/analyze_experiment.py`

```python
#!/usr/bin/env python3
"""
Analyze experiment results and generate statistical report.

Usage:
    python tools/analyze_experiment.py \\
        --experiment-dir experiments/data/exp_20260112_streaming_comparison \\
        --output report.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


class ExperimentAnalyzer:
    """Statistical analysis of experiment results."""

    def __init__(self, experiment_dir: Path):
        self.experiment_dir = experiment_dir
        self.results_path = experiment_dir / "results.json"

        if not self.results_path.exists():
            raise FileNotFoundError(f"Results not found: {self.results_path}")

        with open(self.results_path) as f:
            self.results = json.load(f)

        self.df = self._results_to_dataframe()

    def _results_to_dataframe(self) -> pd.DataFrame:
        """Convert results JSON to pandas DataFrame."""

        rows = []
        for result in self.results:
            row = {
                "round": result["round"],
                "group": result["group"],
                "game_id": result["game_id"],
                "timestamp": result["timestamp"],
            }

            # Flatten metrics
            for metric_name, value in result["metrics"].items():
                row[metric_name] = value

            rows.append(row)

        return pd.DataFrame(rows)

    def compute_descriptive_stats(self, metric: str) -> Dict:
        """Compute descriptive statistics for a metric."""

        control = self.df[self.df["group"] == "control"][metric].dropna()
        treatment = self.df[self.df["group"] == "treatment"][metric].dropna()

        return {
            "control": {
                "n": len(control),
                "mean": control.mean(),
                "std": control.std(),
                "median": control.median(),
                "min": control.min(),
                "max": control.max(),
            },
            "treatment": {
                "n": len(treatment),
                "mean": treatment.mean(),
                "std": treatment.std(),
                "median": treatment.median(),
                "min": treatment.min(),
                "max": treatment.max(),
            }
        }

    def run_ttest(self, metric: str) -> Dict:
        """Run independent samples t-test."""

        control = self.df[self.df["group"] == "control"][metric].dropna()
        treatment = self.df[self.df["group"] == "treatment"][metric].dropna()

        t_stat, p_value = stats.ttest_ind(control, treatment)

        # Cohen's d effect size
        pooled_std = np.sqrt(((len(control) - 1) * control.std()**2 + (len(treatment) - 1) * treatment.std()**2) / (len(control) + len(treatment) - 2))
        cohens_d = (treatment.mean() - control.mean()) / pooled_std

        return {
            "t_statistic": t_stat,
            "p_value": p_value,
            "cohens_d": cohens_d,
            "significant": p_value < 0.05
        }

    def generate_report(self, output_path: Path) -> None:
        """Generate markdown report."""

        metrics = [col for col in self.df.columns if col not in ["round", "group", "game_id", "timestamp"]]

        report_lines = [
            f"# Experiment Analysis: {self.experiment_dir.name}",
            "",
            f"**Date**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Total Rounds**: {len(self.df)}",
            f"**Control Rounds**: {len(self.df[self.df['group'] == 'control'])}",
            f"**Treatment Rounds**: {len(self.df[self.df['group'] == 'treatment'])}",
            "",
            "---",
            "",
            "## Results Summary",
            ""
        ]

        for metric in metrics:
            report_lines.append(f"### {metric}")
            report_lines.append("")

            # Descriptive stats
            stats_dict = self.compute_descriptive_stats(metric)
            control_stats = stats_dict["control"]
            treatment_stats = stats_dict["treatment"]

            report_lines.append(f"**Control**: {control_stats['mean']:.2f} ± {control_stats['std']:.2f} (mean ± SD)")
            report_lines.append(f"**Treatment**: {treatment_stats['mean']:.2f} ± {treatment_stats['std']:.2f}")

            diff_pct = ((treatment_stats['mean'] - control_stats['mean']) / control_stats['mean']) * 100
            report_lines.append(f"**Difference**: {diff_pct:+.1f}%")
            report_lines.append("")

            # Statistical test
            test_result = self.run_ttest(metric)
            report_lines.append(f"**t-test**: t={test_result['t_statistic']:.2f}, p={test_result['p_value']:.4f}")
            report_lines.append(f"**Effect Size**: Cohen's d = {test_result['cohens_d']:.2f}")
            report_lines.append(f"**Significant**: {'✅ Yes (p<0.05)' if test_result['significant'] else '❌ No (p≥0.05)'}")
            report_lines.append("")

        # Write report
        with open(output_path, 'w') as f:
            f.write("\\n".join(report_lines))

        print(f"Report saved to: {output_path}")

    def create_visualizations(self) -> None:
        """Create comparison charts."""

        metrics = [col for col in self.df.columns if col not in ["round", "group", "game_id", "timestamp"]]

        for metric in metrics:
            fig, ax = plt.subplots(figsize=(10, 6))

            control_data = self.df[self.df["group"] == "control"][metric].dropna()
            treatment_data = self.df[self.df["group"] == "treatment"][metric].dropna()

            ax.boxplot([control_data, treatment_data], labels=["Control", "Treatment"])
            ax.set_ylabel(metric)
            ax.set_title(f"{metric} Comparison")
            ax.grid(axis='y', alpha=0.3)

            fig.savefig(self.experiment_dir / f"{metric}_boxplot.png", dpi=150, bbox_inches='tight')
            plt.close(fig)

        print(f"Visualizations saved to: {self.experiment_dir}")


def main():
    parser = argparse.ArgumentParser(description="Analyze experiment results")
    parser.add_argument("--experiment-dir", required=True, help="Experiment data directory")
    parser.add_argument("--output", default="analysis_report.md", help="Output report path")

    args = parser.parse_args()

    experiment_dir = Path(args.experiment_dir)
    analyzer = ExperimentAnalyzer(experiment_dir)

    print("Computing statistics...")
    analyzer.generate_report(Path(args.output))

    print("Creating visualizations...")
    analyzer.create_visualizations()

    print("\\nAnalysis complete!")


if __name__ == "__main__":
    main()
```

---

## Usage Examples

### Example 1: Streaming Mode Comparison

```bash
# Run experiment
python tools/experiment_runner.py \\
  --experiment-id exp_20260112_streaming_comparison \\
  --control-flags '{"streaming_mode": "unary_fallback"}' \\
  --treatment-flags '{"streaming_mode": "bidirectional"}' \\
  --rounds-per-group 30 \\
  --game-mode FFA \\
  --assignment round_robin

# Analyze results
python tools/analyze_experiment.py \\
  --experiment-dir experiments/data/exp_20260112_streaming_comparison \\
  --output experiments/reports/streaming_comparison_report.md
```

### Example 2: Hz Optimization Matrix

```bash
# Test 3 Hz levels (15, 30, 60)
for hz in 15 30 60; do
  python tools/experiment_runner.py \\
    --experiment-id exp_20260112_hz_optimization_${hz}hz \\
    --control-flags '{"update_frequency_hz": 30}' \\
    --treatment-flags "{\"update_frequency_hz\": ${hz}}" \\
    --rounds-per-group 20 \\
    --game-mode FFA
done

# Compare all
python tools/compare_experiments.py \\
  --experiment-dirs experiments/data/exp_20260112_hz_optimization_* \\
  --metric latency_p95 \\
  --output hz_comparison.md
```

### Example 3: Reward System Effectiveness

```bash
# Compare games with/without rewards
python tools/experiment_runner.py \\
  --experiment-id exp_20260112_reward_effectiveness \\
  --control-flags '{"enable_adaptive_rewards": false}' \\
  --treatment-flags '{"enable_adaptive_rewards": true}' \\
  --rounds-per-group 25 \\
  --game-mode FFA

# Analyze player engagement metrics
python tools/analyze_experiment.py \\
  --experiment-dir experiments/data/exp_20260112_reward_effectiveness \\
  --metrics player_warnings_per_game,game_duration,player_satisfaction \\
  --output reward_effectiveness_report.md
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/tools/test_experiment_runner.py`

```python
def test_set_flags_updates_via_api(mock_requests):
    """Test flag updates via Web UI API."""

    runner = ExperimentRunner("test_exp")
    runner.set_flags({"streaming_mode": "bidirectional"})

    mock_requests.post.assert_called_with(
        "http://localhost:8080/api/flags/update",
        json={"flag_key": "streaming_mode", "value": "bidirectional"}
    )


def test_collect_metrics_queries_prometheus(mock_prom):
    """Test Prometheus metric collection."""

    mock_prom.custom_query.return_value = [{"value": [0, "25.5"]}]

    runner = ExperimentRunner("test_exp")
    metrics = runner.collect_metrics("game_123")

    assert "latency_p95" in metrics
    assert metrics["latency_p95"] == 25.5
```

**File**: `tests/unit/tools/test_analyze_experiment.py`

```python
def test_compute_descriptive_stats():
    """Test descriptive statistics calculation."""

    analyzer = ExperimentAnalyzer(Path("tests/fixtures/experiment_data"))
    stats = analyzer.compute_descriptive_stats("latency_p95")

    assert "control" in stats
    assert "treatment" in stats
    assert stats["control"]["mean"] > 0
    assert stats["control"]["std"] > 0


def test_ttest_detects_significant_difference():
    """Test t-test with significant difference."""

    analyzer = ExperimentAnalyzer(Path("tests/fixtures/significant_diff"))
    result = analyzer.run_ttest("latency_p95")

    assert result["significant"] is True
    assert result["p_value"] < 0.05
```

---

## Files to Create

```
tools/
├── experiment_runner.py       # Automated experiment execution
├── analyze_experiment.py      # Statistical analysis
└── compare_experiments.py     # Multi-experiment comparison

experiments/
├── templates/
│   └── experiment_template.md # Experiment documentation template
├── data/                       # Experiment results (gitignored)
└── reports/                    # Generated analysis reports

docs/
└── experimentation-guide.md   # How-to guide for running experiments
```

---

## Success Criteria

- [ ] Experiment runner executes N rounds per group
- [ ] Flags updated via Web UI API before each round
- [ ] Metrics collected from Prometheus after each game
- [ ] Results exported to JSON and CSV
- [ ] Analysis script computes descriptive statistics
- [ ] T-tests run with correct p-values
- [ ] Effect sizes (Cohen's d) calculated
- [ ] Report generated in markdown format
- [ ] Visualizations (boxplots) created
- [ ] Experiment template covers all key sections
- [ ] Documentation guide complete

---

## Next Steps After Phase 54

**Phase 54 completes the experimentation framework!** After this phase:

1. **Run Initial Experiments**:
   - Streaming mode comparison (Phase 45 validation)
   - Hz optimization for 25 controllers
   - Reward system effectiveness

2. **Iterate on Configurations**:
   - Use data-driven insights to tune defaults
   - A/B test new reward strategies
   - Optimize for different demo scenarios

3. **Future Enhancements**:
   - Bayesian optimization for automatic tuning
   - Multi-armed bandit for adaptive experiments
   - Integration with CI/CD for regression testing

---

**End of Phase 54**

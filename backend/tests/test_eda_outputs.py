"""Validation checks for the generated Phase 3 EDA artifacts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


EDA_DIR = Path("data/reports/eda")
CHARTS = [
    "hourly_demand.png",
    "weekday_demand.png",
    "monthly_demand.png",
    "daily_demand_trend.png",
    "top_stations.png",
    "station_utilization.png",
    "occupancy_distribution.png",
    "occupancy_boxplot.png",
    "hour_weekday_heatmap.png",
    "weekday_weekend_comparison.png",
    "occupancy_outliers.png",
]


class EdaOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.overview = json.loads((EDA_DIR / "dataset_overview.json").read_text(encoding="utf-8"))
        cls.hourly = pd.read_csv(EDA_DIR / "hourly_demand.csv")
        cls.weekday = pd.read_csv(EDA_DIR / "weekday_demand.csv")
        cls.monthly = pd.read_csv(EDA_DIR / "monthly_demand.csv")

    def test_overview_matches_phase2_baseline(self) -> None:
        self.assertEqual(self.overview["total_observations"], 1_317_750)
        self.assertEqual(self.overview["total_stations"], 150)
        self.assertTrue(all(self.overview["phase2_reference_matches"].values()))

    def test_grouped_rankings_match_expected_summary_rows(self) -> None:
        self.assertEqual(int(self.hourly.loc[self.hourly["average_occupied_ports"].idxmax(), "hour"]), 17)
        self.assertEqual(int(self.hourly.loc[self.hourly["average_occupied_ports"].idxmin(), "hour"]), 3)
        self.assertEqual(self.weekday.loc[self.weekday["average_occupied_ports"].idxmax(), "weekday_name"], "Monday")
        self.assertEqual(self.weekday.loc[self.weekday["average_occupied_ports"].idxmin(), "weekday_name"], "Sunday")
        self.assertEqual(self.monthly.loc[self.monthly["average_occupied_ports"].idxmax(), "month_name"], "December")

    def test_all_expected_charts_exist_and_are_nonempty(self) -> None:
        for chart in CHARTS:
            path = EDA_DIR / chart
            self.assertTrue(path.exists(), chart)
            self.assertGreater(path.stat().st_size, 0, chart)


if __name__ == "__main__":
    unittest.main()

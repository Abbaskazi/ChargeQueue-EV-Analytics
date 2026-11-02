"""Small deterministic tests for Phase 3 EDA helpers."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.services.eda import iqr_outlier_bounds, summary_statistics


class EdaHelperTests(unittest.TestCase):
    def test_summary_statistics(self) -> None:
        result = summary_statistics(pd.Series([0, 1, 2, 3, 4]))
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["mean"], 2.0)
        self.assertEqual(result["median"], 2.0)
        self.assertEqual(result["q1"], 1.0)
        self.assertEqual(result["q3"], 3.0)

    def test_iqr_bounds(self) -> None:
        q1, q3, iqr, lower, upper = iqr_outlier_bounds(np.array([1, 2, 3, 4, 5, 20]))
        self.assertEqual(q1, 2.25)
        self.assertEqual(q3, 4.75)
        self.assertEqual(iqr, 2.5)
        self.assertEqual(lower, -1.5)
        self.assertEqual(upper, 8.5)


if __name__ == "__main__":
    unittest.main()

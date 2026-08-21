from pathlib import Path

import pandas as pd

from codebase.common_esto_dashboard_data import (
    REQUIRED_COLUMNS,
    load_long_common_esto_data,
)


def test_long_parquet_loader_accepts_categorical_text_columns(tmp_path: Path) -> None:
    values = {
        column: ["value"]
        for column in REQUIRED_COLUMNS
        if column not in {"year", "value"}
    }
    values["year"] = [2022]
    values["value"] = [1.0]
    frame = pd.DataFrame(values)
    frame["scenario"] = pd.Series([None], dtype="category")
    path = tmp_path / "comparison.parquet"
    frame.to_parquet(path, index=False)

    loaded = load_long_common_esto_data(path)

    assert loaded.loc[0, "scenario"] == ""
    assert loaded.loc[0, "year"] == 2022
    assert loaded.loc[0, "value"] == 1.0

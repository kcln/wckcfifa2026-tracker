import pandas as pd
from ml.src import ingest


def test_load_results_parses_columns_and_dates(tmp_path):
    csv = tmp_path / "results.csv"
    csv.write_text(
        "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
        "2018-06-14,Russia,Saudi Arabia,5,0,FIFA World Cup,Moscow,Russia,False\n"
        "2018-06-15,Egypt,Uruguay,0,1,FIFA World Cup,Yekaterinburg,Russia,True\n"
    )
    df = ingest.load_results(csv)
    assert list(df.columns[:6]) == ["date", "home_team", "away_team", "home_score", "away_score", "neutral"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert len(df) == 2
    assert df.iloc[0]["home_team"] == "Russia"
    assert bool(df.iloc[1]["neutral"]) is True


def test_load_results_drops_rows_with_missing_scores(tmp_path):
    csv = tmp_path / "results.csv"
    csv.write_text(
        "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
        "2020-01-01,A,B,1,2,Friendly,X,Y,False\n"
        "2020-01-02,C,D,,,Friendly,X,Y,False\n"
    )
    df = ingest.load_results(csv)
    assert len(df) == 1

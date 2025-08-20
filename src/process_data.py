#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from pathlib import Path
import pandas as pd

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# File paths (fixed)
PPC_FILE = DATA_DIR / "ppc_spend.csv"
EMAIL_FILE = DATA_DIR / "email_campaigns.csv"
SOCIAL_FILE = DATA_DIR / "social_media_ads.csv"
CONV_FILE = DATA_DIR / "website_conversions.csv"

OUT_DAILY = DATA_DIR / "aggregated_daily.csv"
OUT_WEEKLY = DATA_DIR / "aggregated_weekly.csv"

DATE_COL = "date"

def load_ppc(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'date' not in df.columns:
        raise ValueError('every dateframe should have the date column, problem in PPC')
    df[DATE_COL] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df['channel'] = 'PPC'
    
    # Estimate clicks if missing
    ESTIMATED_CPC = 2.0  # CAD per click
    # Typical CPC range is between 0.5 to 5.00 so I use the Avg
    
    if "clicks" not in df.columns or df["clicks"].isna().all():
        df["clicks"] = (df["spend"] / ESTIMATED_CPC).round()

    return df
    
def load_email(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'date' not in df.columns:
        raise ValueError('every dateframe should have the date column, problem in Email')
    df[DATE_COL] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df['channel'] = 'Email'
    
    # Assume $30 CPM for estimation
    CPM_RATE = 30.0  # CAD per 1000 emails 
    # Range is 5 to 50 so I use Avg
    
    if "spend" not in df.columns or df["spend"].isna().all():
        df["spend"] = df["emails_sent"] * (CPM_RATE / 1000.0)
    return df 

def load_social(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'date' not in df.columns:
        raise ValueError('every dateframe should have the date column, problem in Social Media')
    df[DATE_COL] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df['channel'] = 'Social Media'
    return df
    

def load_conversions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'date' not in df.columns:
        raise ValueError('every dateframe should have the date column')
    df[DATE_COL] = pd.to_datetime(df["date"], errors="coerce").dt.date
    
    # load_conversions()
    df = (
        df.groupby(['date','channel'], as_index=False)
            .agg(
                revenue=('revenue','sum'),
                conversions=('conversion_id','nunique')
            )
)
    print(df) 
    return df


def coalesce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        else:
            df[c] = 0.0
    return df

def integrate(ppc: pd.DataFrame, email: pd.DataFrame,
              social: pd.DataFrame, conv: pd.DataFrame) -> pd.DataFrame:
    """
    Combine channel tables into one standardized long table, then left-join revenue/conversions.
    """
    # Ensure standard numeric columns present
    for df in (ppc, email, social):
        for c in [DATE_COL, "channel"]:
            if c not in df.columns:
                raise ValueError(f"Missing {c} in one of the channel dataframes.")
    # Harmonize columns
    common_cols = ["spend", "clicks", "conversion_id", "revenue", "emails_sent", "impressions"]
    ppc = coalesce_numeric(ppc, ["spend", "clicks"])
    email = coalesce_numeric(email, ["spend", "clicks"])
    social = coalesce_numeric(social, ["spend", "clicks", "impressions"])

    # Union rows (stack)
    base = pd.concat(
        [
            ppc[[DATE_COL, "channel", "spend", "clicks"]].assign(emails_sent=0.0, impressions=0.0),
            email[[DATE_COL, "channel", "spend", "clicks", "emails_sent"]]
            .assign(impressions=0.0),
            social[[DATE_COL, "channel", "spend", "clicks", "impressions"]]
            .assign(emails_sent=0.0),
        ],
        ignore_index=True,
    )
    print("Base DataFrame after stacking channels:" , base.head())
  
    
    merged = base.merge(
    conv, on=['date','channel'], how='left'
)
  
 
    # # Prefer conversions/revenue from website log when present
    # for c in ["revenue", "conversion_id"]:
    #     merged[c] = merged[f"{c}_from_log"].fillna(merged[c]).fillna(0.0)
    #     merged.drop(columns=[f"{c}_from_log"], inplace=True)

    # Final numeric cleanup
    merged = coalesce_numeric(
        merged, ["spend", "clicks", "revenue", "emails_sent", "impressions"]
    )

    # Sort and return
    merged = merged.sort_values([DATE_COL, "channel"]).reset_index(drop=True)
    return merged


def add_time_granularities(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # 1) Daily is just a copy
    daily = df.copy()

    # 2) Make sure "date" is a proper datetime (handles day-first formats)
    daily[DATE_COL] = pd.to_datetime(daily[DATE_COL], errors="coerce", dayfirst=True)

    # 3) Weekly rollup with week starting Monday (W-MON). Change to W-SUN if you prefer.
    weekly = (
        daily
        .groupby([pd.Grouper(key=DATE_COL, freq="W-MON"), "channel"], as_index=False)
        .sum(numeric_only=True)
        .rename(columns={DATE_COL: "week_start"})
    )

    # Optional: convert week_start to simple date (YYYY-MM-DD) instead of full timestamp
    weekly["week_start"] = weekly["week_start"].dt.date
    # Keep the same column name as daily for convenience:
    weekly = weekly.rename(columns={"week_start": DATE_COL})

    return daily, weekly





def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logging.info("Loading source files...")
    ppc = load_ppc(PPC_FILE)
    email = load_email(EMAIL_FILE)
    social = load_social(SOCIAL_FILE)
    conv = load_conversions(CONV_FILE)
    
    logging.info("Printing the dfs......")
    print(ppc)
    print(email)
    print(social)
    

    logging.info("Integrating sources...")
    merged = integrate(ppc, email, social, conv)

    logging.info("Printing merged DF...")
    print(merged)
   
    logging.info("Adding daily/weekly outputs...")
    daily, weekly = add_time_granularities(merged)

    daily.to_csv(OUT_DAILY, index=False)
    weekly.to_csv(OUT_WEEKLY, index=False)

    logging.info("Done. Files saved in %s", DATA_DIR)


if __name__ == "__main__":
    main()

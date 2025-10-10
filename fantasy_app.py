import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# --- Config ---
st.set_page_config(page_title="NFL Team Stats Dashboard", layout="wide")

st.title("🏈 NFL Team Stats Dashboard")
st.caption("Live stats scraped from [TeamRankings.com](https://www.teamrankings.com/nfl/stat/)")
st.markdown("---")

# --- Constants ---
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    )
}

STAT_PAGES = {
    "Opponent Rushing Yards per Game": "opponent-rushing-yards-per-game",
    "Opponent Passing Yards per Game": "opponent-passing-yards-per-game",
    "Red Zone Scoring Attempts per Game": "red-zone-scoring-attempts-per-game",
    "Red Zone Scoring %": "red-zone-scoring-pct",
    "Opponent Red Zone Attempts per Game": "opponent-red-zone-scoring-attempts-per-game",
    "Opponent Red Zone Scoring %": "opponent-red-zone-scoring-pct",
    "Time of Possession % (Net of OT)": "time-of-possession-pct-net-of-ot"
}

BASE_URL = "https://www.teamrankings.com/nfl/stat/"
SCHEDULE_URL = "https://www.teamrankings.com/nfl/schedules/season/"

# --- Helpers ---
def safe_to_float(x):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except:
        return None

def convert_numeric(df):
    for col in df.columns:
        if col != "Team":
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("%", "")
                .replace(["—", "-", "", "None", "nan"], None)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# --- Scraper Functions ---
def scrape_stat_page(url, stat_name):
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return None, f"No table found for {stat_name}"

        headers = [th.text.strip() for th in table.find_all("th")]
        rows = [
            [td.text.strip() for td in row.find_all("td")]
            for row in table.find_all("tr")[1:]
            if row.find_all("td")
        ]
        df = pd.DataFrame(rows, columns=headers)
        df = df.drop(columns=[col for col in df.columns if col in ["Home", "Away", "2024", "Rank"]], errors="ignore")

        team_col = next((col for col in df.columns if "team" in col.lower()), None)
        stat_col = next((col for col in df.columns if col != team_col and not "last 3" in col.lower()), None)
        last3_col = next((col for col in df.columns if "last 3" in col.lower()), None)

        if not team_col or not stat_col:
            return None, f"Could not find Team or Stat column for {stat_name}"

        cols_to_keep = [team_col, stat_col]
        if last3_col:
            cols_to_keep.append(last3_col)

        df = df[cols_to_keep].copy()
        rename_map = {team_col: "Team", stat_col: stat_name}
        if last3_col:
            rename_map[last3_col] = f"{stat_name} (Last 3)"
        df = df.rename(columns=rename_map)

        df = convert_numeric(df)
        return df, None

    except Exception as e:
        return None, f"Error scraping {stat_name}: {e}"

def scrape_all_stats():
    all_dfs = []
    errors = []

    for stat_name, slug in STAT_PAGES.items():
        url = BASE_URL + slug
        df, err = scrape_stat_page(url, stat_name)
        if err:
            errors.append(err)
        elif df is not None:
            all_dfs.append(df)
        time.sleep(1)

    if not all_dfs:
        return pd.DataFrame(), errors

    merged_df = all_dfs[0]
    for df in all_dfs[1:]:
        merged_df = pd.merge(merged_df, df, on="Team", how="outer")

    # Derived % difference columns
    if "Opponent Rushing Yards per Game" in merged_df.columns and "Opponent Rushing Yards per Game (Last 3)" in merged_df.columns:
        merged_df["Opponent Rushing Yards per Game Δ% (Last 3)"] = (
            (merged_df["Opponent Rushing Yards per Game (Last 3)"] - merged_df["Opponent Rushing Yards per Game"])
            / merged_df["Opponent Rushing Yards per Game"]
        ) * 100

    if "Opponent Passing Yards per Game" in merged_df.columns and "Opponent Passing Yards per Game (Last 3)" in merged_df.columns:
        merged_df["Opponent Passing Yards per Game Δ% (Last 3)"] = (
            (merged_df["Opponent Passing Yards per Game (Last 3)"] - merged_df["Opponent Passing Yards per Game"])
            / merged_df["Opponent Passing Yards per Game"]
        ) * 100

    # Reorder columns
    def reorder_columns(df):
        cols = list(df.columns)
        for base in ["Opponent Rushing Yards per Game", "Opponent Passing Yards per Game"]:
            last3 = f"{base} (Last 3)"
            delta = f"{base} Δ% (Last 3)"
            if last3 in cols and delta in cols:
                last3_idx = cols.index(last3)
                cols.insert(last3_idx + 1, cols.pop(cols.index(delta)))
        return df[cols]

    merged_df = reorder_columns(merged_df)
    return merged_df, errors

def scrape_schedule():
    try:
        resp = requests.get(SCHEDULE_URL, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return pd.DataFrame(), "No schedule table found."
        df = pd.read_html(str(table))[0]
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"Error scraping schedule: {e}"

# --- Color Function ---
def highlight_trends(row):
    styles = [""] * len(row)
    columns = list(row.index)

    if "Opponent Rushing Yards per Game" in columns and "Opponent Rushing Yards per Game Δ% (Last 3)" in columns:
        rush_val = row["Opponent Rushing Yards per Game"]
        rush_diff = row["Opponent Rushing Yards per Game Δ% (Last 3)"]
        if pd.notnull(rush_val) and pd.notnull(rush_diff):
            if rush_val > 100 and abs(rush_diff) < 10:
                styles[columns.index("Opponent Rushing Yards per Game Δ% (Last 3)")] = "background-color: lightgreen; color: black;"

    if "Opponent Passing Yards per Game" in columns and "Opponent Passing Yards per Game Δ% (Last 3)" in columns:
        pass_val = row["Opponent Passing Yards per Game"]
        pass_diff = row["Opponent Passing Yards per Game Δ% (Last 3)"]
        if pd.notnull(pass_val) and pd.notnull(pass_diff):
            if pass_val > 200 and abs(pass_diff) < 10:
                styles[columns.index("Opponent Passing Yards per Game Δ% (Last 3)")] = "background-color: lightgreen; color: black;"

    return styles

# --- Load Stats and Schedule ---
with st.spinner("🔄 Scraping stats and schedule..."):
    schedule_df, schedule_err = scrape_schedule()
    df, scrape_errors = scrape_all_stats()

# --- Display Schedule ---
if not schedule_df.empty:
    st.subheader("📅 NFL Schedule")
    st.dataframe(schedule_df, use_container_width=True)
elif schedule_err:
    st.warning(f"⚠️ {schedule_err}")

st.markdown("---")

# --- Display Stats ---
if df.empty:
    st.error("❌ No data was loaded. Check error messages below.")
else:
    st.success("✅ Stats loaded!")

    st.sidebar.header("📋 Choose Stats to Display")
    stat_columns = [col for col in df.columns if col != "Team"]
    selected_stats = [col for col in stat_columns if st.sidebar.checkbox(col, value=True)]

    st.sidebar.header("🟢 Filter Green Highlighted Teams")
    filter_rushing = st.sidebar.checkbox("Show only green Rushing Teams")
    filter_passing = st.sidebar.checkbox("Show only green Passing Teams")

    if not selected_stats:
        st.warning("⚠️ Please select at least one stat from the sidebar.")
    else:
        display_df = df[["Team"] + selected_stats]
        filtered_df = display_df.copy()
        if filter_rushing:
            if "Opponent Rushing Yards per Game" in filtered_df.columns and "Opponent Rushing Yards per Game Δ% (Last 3)" in filtered_df.columns:
                filtered_df = filtered_df[
                    (filtered_df["Opponent Rushing Yards per Game"] > 100) &
                    (filtered_df["Opponent Rushing Yards per Game Δ% (Last 3)"].abs() < 10)
                ]
        if filter_passing:
            if "Opponent Passing Yards per Game" in filtered_df.columns and "Opponent Passing Yards per Game Δ% (Last 3)" in filtered_df.columns:
                filtered_df = filtered_df[
                    (filtered_df["Opponent Passing Yards per Game"] > 200) &
                    (filtered_df["Opponent Passing Yards per Game Δ% (Last 3)"].abs() < 10)
                ]

        styled_df = filtered_df.style.apply(highlight_trends, axis=1)\
            .format({col: "{:.0f}" for col in filtered_df.columns if col != "Team" and "%" not in col})\
            .format({col: "{:.0f}%" for col in filtered_df.columns if "%" in col})

        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={"Team": st.column_config.TextColumn("Team", pinned=True)}
        )

        csv = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv, "nfl_team_stats.csv", "text/csv")

# --- Errors ---
if scrape_errors:
    with st.expander("⚠️ View scraping errors"):
        for err in scrape_errors:
            st.text(err)

st.markdown("---")
st.caption("Built with ❤️ using Streamlit + BeautifulSoup • [TeamRankings.com](https://www.teamrankings.com)")

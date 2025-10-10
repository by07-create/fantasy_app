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
    # Added new stat
    "Touchdowns per Game": "touchdowns-per-game",
    "Opponent Touchdowns per Game": "opponent-touchdowns-per-game",
    "Opponent Rushing Yards per Game": "opponent-rushing-yards-per-game",
    "Opponent Passing Yards per Game": "opponent-passing-yards-per-game",
    "Red Zone Scoring Attempts per Game": "red-zone-scoring-attempts-per-game",
    "Red Zone Scoring %": "red-zone-scoring-pct",
    "Opponent Red Zone Attempts per Game": "opponent-red-zone-scoring-attempts-per-game",
    "Opponent Red Zone Scoring %": "opponent-red-zone-scoring-pct",
    "Time of Possession % (Net of OT)": "time-of-possession-pct-net-of-ot",
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


# --- Scrape Functions ---
def scrape_table(url, stat_name):
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
        df, err = scrape_table(url, stat_name)
        if err:
            errors.append(err)
        elif df is not None:
            all_dfs.append(df)
        time.sleep(1)

    if not all_dfs:
        return pd.DataFrame(), errors

    merged = all_dfs[0]
    for df in all_dfs[1:]:
        merged = pd.merge(merged, df, on="Team", how="outer")

    # Derived Δ% columns
    for base in ["Opponent Rushing Yards per Game", "Opponent Passing Yards per Game"]:
        if base in merged.columns and f"{base} (Last 3)" in merged.columns:
            merged[f"{base} Δ% (Last 3)"] = (
                (merged[f"{base} (Last 3)"] - merged[base]) / merged[base]
            ) * 100

    def reorder(df):
        cols = list(df.columns)
        for base in ["Opponent Rushing Yards per Game", "Opponent Passing Yards per Game"]:
            last3 = f"{base} (Last 3)"
            delta = f"{base} Δ% (Last 3)"
            if last3 in cols and delta in cols:
                last3_idx = cols.index(last3)
                cols.insert(last3_idx + 1, cols.pop(cols.index(delta)))
        return df[cols]

    merged = reorder(merged)
    return merged, errors


def scrape_schedule():
    try:
        resp = requests.get(SCHEDULE_URL, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if table:
            df = pd.read_html(str(table), flavor="bs4")[0]
            return df, None
        return None, "No schedule table found."
    except Exception as e:
        return None, f"Error scraping schedule: {e}"


# --- Highlight Function ---
def highlight_trends(row):
    styles = [""] * len(row)
    cols = list(row.index)

    # Rushing
    if "Opponent Rushing Yards per Game" in cols and "Opponent Rushing Yards per Game Δ% (Last 3)" in cols:
        rush_val = row["Opponent Rushing Yards per Game"]
        rush_diff = row["Opponent Rushing Yards per Game Δ% (Last 3)"]
        if pd.notnull(rush_val) and pd.notnull(rush_diff):
            if rush_val > 100 and abs(rush_diff) < 10:
                styles[cols.index("Opponent Rushing Yards per Game Δ% (Last 3)")] = "background-color: lightgreen; color: black;"

    # Passing
    if "Opponent Passing Yards per Game" in cols and "Opponent Passing Yards per Game Δ% (Last 3)" in cols:
        pass_val = row["Opponent Passing Yards per Game"]
        pass_diff = row["Opponent Passing Yards per Game Δ% (Last 3)"]
        if pd.notnull(pass_val) and pd.notnull(pass_diff):
            if pass_val > 200 and abs(pass_diff) < 10:
                styles[cols.index("Opponent Passing Yards per Game Δ% (Last 3)")] = "background-color: lightgreen; color: black;"

    return styles


# --- Load Data ---
with st.spinner("🔄 Loading NFL schedule..."):
    schedule_df, schedule_err = scrape_schedule()

if schedule_df is not None:
    st.subheader("📅 NFL Schedule")
    st.dataframe(schedule_df, use_container_width=True, hide_index=True)
else:
    st.warning(f"⚠️ {schedule_err}")

st.markdown("---")

with st.spinner("🔄 Scraping stats..."):
    df, scrape_errs = scrape_all_stats()

if df.empty:
    st.error("❌ No data loaded. Check errors below.")
else:
    st.success("✅ Stats loaded!")

    st.sidebar.header("📋 Choose Stats to Display")
    stat_cols = [col for col in df.columns if col != "Team"]
    selected_stats = [col for col in stat_cols if st.sidebar.checkbox(col, value=True)]

    st.sidebar.header("🟢 Filter Green Highlighted Teams")
    filter_rush = st.sidebar.checkbox("Show only green Rushing Teams")
    filter_pass = st.sidebar.checkbox("Show only green Passing Teams")

    if not selected_stats:
        st.warning("⚠️ Please select at least one stat.")
    else:
        filtered_df = df[["Team"] + selected_stats].copy()

        if filter_rush:
            filtered_df = filtered_df[
                (filtered_df["Opponent Rushing Yards per Game"] > 100)
                & (filtered_df["Opponent Rushing Yards per Game Δ% (Last 3)"].abs() < 10)
            ]
        if filter_pass:
            filtered_df = filtered_df[
                (filtered_df["Opponent Passing Yards per Game"] > 200)
                & (filtered_df["Opponent Passing Yards per Game Δ% (Last 3)"].abs() < 10)
            ]

        # Split into offense & defense
        offense_cols = [
            "Touchdowns per Game",
            "Touchdowns per Game (Last 3)",
            "Red Zone Scoring Attempts per Game",
            "Red Zone Scoring Attempts per Game (Last 3)",
            "Red Zone Scoring %",
            "Red Zone Scoring % (Last 3)",
            "Time of Possession % (Net of OT)",
            "Time of Possession % (Net of OT) (Last 3)",
        ]
        offense_cols = [c for c in offense_cols if c in filtered_df.columns]
        defense_cols = [c for c in filtered_df.columns if c not in offense_cols + ["Team"]]

        # ✅ FIXED REORDER: safer logic to always group Opponent Touchdowns after Passing Yards (Last 3)
        if "Opponent Passing Yards per Game (Last 3)" in defense_cols:
            pass_last3_idx = defense_cols.index("Opponent Passing Yards per Game (Last 3)")

            if "Opponent Touchdowns per Game" in defense_cols:
                defense_cols.insert(pass_last3_idx + 1, defense_cols.pop(defense_cols.index("Opponent Touchdowns per Game")))
                pass_last3_idx += 1

            if "Opponent Touchdowns per Game (Last 3)" in defense_cols:
                defense_cols.insert(pass_last3_idx + 1, defense_cols.pop(defense_cols.index("Opponent Touchdowns per Game (Last 3)")))

        offense_df = filtered_df[["Team"] + offense_cols] if offense_cols else pd.DataFrame()
        defense_df = filtered_df[["Team"] + defense_cols] if defense_cols else pd.DataFrame()

        # --- Offense Table ---
        st.subheader("⚙️ Offensive Stats")
        if not offense_df.empty:
            st.dataframe(
                offense_df.style.format(
                    {c: "{:.0f}" for c in offense_df.columns if "%" not in c and c != "Team"}
                ).format(
                    {c: "{:.0f}%" for c in offense_df.columns if "%" in c}
                ),
                use_container_width=True,
                hide_index=True,
                column_config={"Team": st.column_config.TextColumn("Team", pinned=True)},
            )
        else:
            st.info("No offensive stats available.")

        # --- Defense Table ---
        st.subheader("🛡️ Defensive Stats")
        if not defense_df.empty:
            styled_def = defense_df.style.apply(highlight_trends, axis=1)\
                .format({c: "{:.0f}" for c in defense_df.columns if "%" not in c and c != "Team"})\
                .format({c: "{:.0f}%" for c in defense_df.columns if "%" in c})

            st.dataframe(
                styled_def,
                use_container_width=True,
                hide_index=True,
                column_config={"Team": st.column_config.TextColumn("Team", pinned=True)},
            )
        else:
            st.info("No defensive stats available.")

        # --- Download ---
        csv = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv, "nfl_team_stats.csv", "text/csv")

# --- Errors ---
if scrape_errs:
    with st.expander("⚠️ View scraping errors"):
        for e in scrape_errs:
            st.text(e)

st.markdown("---")
st.caption("Built with ❤️ using Streamlit + BeautifulSoup • Data from [TeamRankings.com](https://www.teamrankings.com)")

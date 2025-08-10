import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import plotly.express as px

st.set_page_config(page_title="Turf Map", layout="wide")
st.title("Turf Mapping")

# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data
def load_metrics():
    df = pd.read_csv("output/precincts_metrics_updated.csv")
    df["van_precinct_id"] = df["van_precinct_id"].astype(str)
    return df

@st.cache_data
def load_geojson():
    with open("output/precincts_simplified_updated.geojson", "r") as f:
        data = json.load(f)
    for feature in data["features"]:
        feature["properties"]["van_precinct_id"] = str(feature["properties"]["van_precinct_id"])
    return data

# -----------------------------
# Load data
# -----------------------------
df_metrics = load_metrics()
geojson_data = load_geojson()

# -----------------------------
# Sidebar: filters only
# -----------------------------
with st.sidebar:
    st.header("Filters")

    regions = sorted(df_metrics["Current Region"].dropna().unique())
    regions_with_all = ["VA All Regions"] + regions

    selected_regions_raw = st.multiselect("Select Region(s):", regions_with_all, default=["VA All Regions"])
    if "VA All Regions" in selected_regions_raw:
        selected_regions = regions
    else:
        selected_regions = [r for r in selected_regions_raw if r != "VA All Regions"]

    if selected_regions:
        available_turfs = sorted(
            df_metrics[df_metrics["Current Region"].isin(selected_regions)]["Current Turf"].dropna().unique()
        )
        selected_turfs = st.multiselect("Select Turf(s):", available_turfs, default=[])
    else:
        selected_turfs = []

# -----------------------------
# Filter for view
# -----------------------------
if selected_regions:
    filtered_metrics = df_metrics[df_metrics["Current Region"].isin(selected_regions)].copy()
    if selected_turfs:
        filtered_metrics = filtered_metrics[filtered_metrics["Current Turf"].isin(selected_turfs)]
else:
    filtered_metrics = pd.DataFrame(columns=df_metrics.columns).copy()

# -----------------------------
# KPIs
# -----------------------------
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Precincts in Filter", f"{len(filtered_metrics):,}")
with c2:
    st.metric(
        "Total Voters in Filter",
        f"{int(filtered_metrics['voters'].sum()):,}" if "voters" in filtered_metrics.columns else "0",
    )
with c3:
    if {"supporters", "voters"}.issubset(filtered_metrics.columns) and filtered_metrics["voters"].sum() > 0:
        st.metric("Support Rate", f"{(filtered_metrics['supporters'].sum()/filtered_metrics['voters'].sum()):.1%}")
    else:
        st.metric("Support Rate", "N/A")

# -----------------------------
# Colors for turfs (map + charts)
# -----------------------------
palette = [
    "#e41a1c","#377eb8","#4daf4a","#984ea3","#ff7f00",
    "#ffff33","#a65628","#f781bf","#999999","#66c2a5",
    "#fc8d62","#8da0cb","#e78ac3","#a6d854","#ffd92f",
    "#e5c494","#b3b3b3","#1b9e77","#d95f02","#7570b3",
]
unique_turfs = sorted(filtered_metrics["Current Turf"].dropna().unique()) if len(filtered_metrics) else []
turf_colors_map = {t: palette[i % len(palette)] for i, t in enumerate(unique_turfs)}

# -----------------------------
# Map (Folium)
# -----------------------------
m = folium.Map(location=[37.5407, -77.4360], zoom_start=7, prefer_canvas=True)

filtered_features = []
if len(filtered_metrics) > 0:
    selected_ids = set(filtered_metrics["van_precinct_id"])
    filtered_features = [f for f in geojson_data["features"] if f["properties"]["van_precinct_id"] in selected_ids]

    if filtered_features and {"min_lat", "min_lon", "max_lat", "max_lon"}.issubset(filtered_metrics.columns):
        bounds = [
            [filtered_metrics["min_lat"].min(), filtered_metrics["min_lon"].min()],
            [filtered_metrics["max_lat"].max(), filtered_metrics["max_lon"].max()],
        ]
        m.fit_bounds(bounds)

    if filtered_features:
        filtered_geojson = {"type": "FeatureCollection", "features": filtered_features}
        folium.GeoJson(
            filtered_geojson,
            style_function=lambda x: {
                "fillColor": turf_colors_map.get(x["properties"].get("Current Turf"), "#3388ff"),
                "color": "#000",
                "weight": 0.5,
                "fillOpacity": 0.6,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[
                    "van_precinct_name",
                    "van_precinct_id",
                    "county_name",
                    "Current Region",
                    "Current Turf",
                    *(["voters"] if "voters" in filtered_metrics.columns else []),
                    *(["supporters"] if "supporters" in filtered_metrics.columns else []),
                ],
                aliases=[
                    "Precinct Name:",
                    "Precinct ID:",
                    "County:",
                    "Region:",
                    "Turf:",
                    *(["Voters:"] if "voters" in filtered_metrics.columns else []),
                    *(["Supporters:"] if "supporters" in filtered_metrics.columns else []),
                ],
                localize=True,
            ) if len(filtered_features) < 1000 else None,
        ).add_to(m)

st_folium(m, key="map", width=None, height=600, returned_objects=[])

# =========================================================
# Section 1: Precincts in selection (table + checkbox + DL)
# =========================================================
if len(filtered_metrics) > 0:
    st.subheader("Precincts in selection")
    table_cols = [
        "Current Turf",
        "van_precinct_name",
        "van_precinct_id",
        "county_name",
        *(["voters"] if "voters" in filtered_metrics.columns else []),
        *(["supporters"] if "supporters" in filtered_metrics.columns else []),
    ]
    precinct_table = (
        filtered_metrics[table_cols]
        .sort_values(["Current Turf", "van_precinct_name"], ascending=[True, True])
        .reset_index(drop=True)
    )
    st.dataframe(precinct_table, use_container_width=True, hide_index=True)

    # Small download button for this table
    st.download_button(
        "Download table as CSV",
        data=precinct_table.to_csv(index=False),
        file_name="precincts_in_selection.csv",
        mime="text/csv",
        use_container_width=False,
    )

    # Checkbox + chart (voter distribution by precinct)
    show_precinct_hist = st.checkbox("Show voter distribution by precinct", value=False, key="show_precincts_chart")
    if show_precinct_hist and "voters" in filtered_metrics.columns:
        hist_df = filtered_metrics.sort_values(["Current Turf", "van_precinct_name"]).copy()
        hist_df["display_name"] = hist_df["van_precinct_name"]
        # color map aligned with the map colors
        all_turfs = sorted(hist_df["Current Turf"].dropna().unique())
        color_map_precinct = {t: turf_colors_map.get(t, palette[i % len(palette)]) for i, t in enumerate(all_turfs)}

        fig_precincts = px.bar(
            hist_df,
            x="display_name",
            y="voters",
            color="Current Turf",
            color_discrete_map=color_map_precinct,
            labels={"display_name": "Precinct", "voters": "Voters"},
            title="Voter Distribution by Precinct",
            height=420,
        )
        fig_precincts.update_layout(
            xaxis_tickangle=-45, showlegend=True, xaxis_title="Precinct", yaxis_title="Number of Voters"
        )
        st.plotly_chart(fig_precincts, use_container_width=True)

# =====================================================
# Section 2: Breakdown by Turf (table + checkbox + DL)
# =====================================================
if len(filtered_metrics) > 0:
    st.subheader("Breakdown by Turf")

    turf_summary = (
        filtered_metrics.groupby("Current Turf")
        .agg(
            voters=("voters", "sum") if "voters" in filtered_metrics.columns else ("van_precinct_id", "size"),
            supporters=("supporters", "sum") if "supporters" in filtered_metrics.columns else ("van_precinct_id", "size"),
            precinct_count=("van_precinct_id", "count"),
        )
        .sort_index()
    )
    st.dataframe(turf_summary, use_container_width=True)

    # Small download button for this breakdown table
    st.download_button(
        "Download breakdown as CSV",
        data=turf_summary.reset_index().to_csv(index=False),
        file_name="breakdown_by_turf.csv",
        mime="text/csv",
        use_container_width=False,
    )

    # Checkbox + chart (compare turfs)
    compare_turfs = st.checkbox("Compare turfs in filter", value=False, key="compare_turfs_chart")
    if compare_turfs and "voters" in filtered_metrics.columns:
        agg_turf = (
            filtered_metrics.groupby("Current Turf", as_index=False)["voters"]
            .sum()
            .sort_values("Current Turf", ascending=True)
        )
        # Use same colors as map
        fig_turf = px.bar(
            agg_turf,
            x="Current Turf",
            y="voters",
            color="Current Turf",
            color_discrete_map=turf_colors_map,
            title="Voters by Turf",
            height=380,
            labels={"Current Turf": "Turf", "voters": "Voters"},
        )
        fig_turf.update_layout(showlegend=False, xaxis_title="Turf", yaxis_title="Voters")
        st.plotly_chart(fig_turf, use_container_width=True)
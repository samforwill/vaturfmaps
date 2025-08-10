import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
from pathlib import Path
import plotly.express as px

st.set_page_config(page_title="Turf Viewer", layout="wide")
st.title("Turf Map Viewer")

DATA_DIR = Path("output")
METRICS_CSV = DATA_DIR / "precincts_metrics_updated.csv"
REGION_DIR = DATA_DIR / "regions"

# -----------------------------
# Data Loading
# -----------------------------
@st.cache_data
def load_metrics_minimal():
    """Load only essential columns"""
    cols_needed = ["van_precinct_id", "Current Region", "Current Turf", 
                   "min_lat", "min_lon", "max_lat", "max_lon", 
                   "voters", "supporters", "van_precinct_name"]
    
    try:
        df = pd.read_csv(METRICS_CSV, usecols=lambda x: x in cols_needed, 
                        dtype={'van_precinct_id': str})
        df["Current Region"] = df["Current Region"].fillna("")
        df["Current Turf"] = df["Current Turf"].fillna("")
        return df
    except:
        df = pd.read_csv(METRICS_CSV, dtype={'van_precinct_id': str})
        df["Current Region"] = df["Current Region"].fillna("")
        df["Current Turf"] = df["Current Turf"].fillna("")
        return df

@st.cache_data
def load_single_region_geojson(region_code: str):
    """Load only the specific region's GeoJSON"""
    if region_code == "ALL":
        path = DATA_DIR / "precincts_simplified_updated.geojson"
    else:
        safe_code = region_code.replace(" ", "_").replace("/", "_")
        path = REGION_DIR / f"{safe_code}_updated.geojson"
        
        if not path.exists():
            import re
            m = re.search(r"R\d{2}", region_code)
            if m:
                path = REGION_DIR / f"{m.group(0)}_updated.geojson"
        
        if not path.exists():
            return None
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
        
        for feat in data["features"]:
            feat["properties"]["van_precinct_id"] = str(feat["properties"]["van_precinct_id"])
        
        return data
    except:
        return None

# -----------------------------
# Load metrics
# -----------------------------
df = load_metrics_minimal()

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Select Area to View")
    
    regions = sorted([r for r in df["Current Region"].unique() if r])
    
    selected_region = st.selectbox(
        "Select Region",
        ["All Regions"] + regions,
        index=0
    )
    
    if selected_region == "All Regions":
        available_turfs = sorted([t for t in df["Current Turf"].unique() if t])
        filtered_base = df
    else:
        filtered_base = df[df["Current Region"] == selected_region]
        available_turfs = sorted([t for t in filtered_base["Current Turf"].unique() if t])
    
    selected_turfs = st.multiselect(
        "Filter by Turf(s)",
        available_turfs,
        default=[]
    )
    
    st.divider()
    
    show_turf_chart = st.checkbox("Show turf chart", value=False)
    show_precinct_chart = st.checkbox("Show precinct chart", value=False)

# -----------------------------
# Filter data
# -----------------------------
if selected_region == "All Regions":
    filtered = filtered_base.copy()
    region_to_load = "ALL"
else:
    filtered = filtered_base.copy()
    region_to_load = selected_region

if selected_turfs:
    filtered = filtered[filtered["Current Turf"].isin(selected_turfs)]

# -----------------------------
# KPIs
# -----------------------------
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Precincts", f"{len(filtered):,}")
with col2:
    if "voters" in filtered.columns:
        st.metric("Total Voters", f"{int(filtered['voters'].sum()):,}")
with col3:
    n_turfs = filtered["Current Turf"].nunique()
    st.metric("Turfs Shown", n_turfs)

# -----------------------------
# Map
# -----------------------------
if len(filtered) > 0 and all(c in filtered.columns for c in ["min_lat", "min_lon", "max_lat", "max_lon"]):
    bounds = [
        [filtered["min_lat"].min(), filtered["min_lon"].min()],
        [filtered["max_lat"].max(), filtered["max_lon"].max()]
    ]
    center = [(bounds[0][0] + bounds[1][0])/2, (bounds[0][1] + bounds[1][1])/2]
    
    span = max(bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1])
    zoom = 12 if span < 0.1 else 10 if span < 0.5 else 8 if span < 2 else 7
else:
    center = [37.5407, -77.4360]
    zoom = 7
    bounds = None

m = folium.Map(location=center, zoom_start=zoom, prefer_canvas=True)

if len(filtered) > 0:
    with st.spinner(f"Loading map data for {len(filtered)} precincts..."):
        geojson_data = load_single_region_geojson(region_to_load)
        
        if geojson_data:
            selected_ids = set(filtered["van_precinct_id"].astype(str))
            filtered_features = [
                f for f in geojson_data["features"] 
                if f["properties"]["van_precinct_id"] in selected_ids
            ]
            
            if filtered_features:
                unique_turfs = sorted(set(f["properties"].get("Current Turf", "") 
                                        for f in filtered_features if f["properties"].get("Current Turf")))
                palette = [
                    '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
                    '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
                    '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
                    '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3'
                ]
                turf_colors = {t: palette[i % len(palette)] for i, t in enumerate(unique_turfs)}
                
                filtered_geojson = {"type": "FeatureCollection", "features": filtered_features}
                
                style_func = lambda x: {
                    "fillColor": turf_colors.get(x["properties"].get("Current Turf", ""), "#3388ff"),
                    "color": "#000",
                    "weight": 0.5,
                    "fillOpacity": 0.7,
                }
                
                geojson_layer = folium.GeoJson(
                    filtered_geojson,
                    style_function=style_func,
                    tooltip=folium.GeoJsonTooltip(
                        fields=["van_precinct_name", "Current Turf", "voters"],
                        aliases=["Precinct:", "Turf:", "Voters:"],
                        localize=True,
                        sticky=True,
                        labels=True,
                        max_width=200
                    ) if len(filtered_features) < 500 else None,
                ).add_to(m)
                
                if bounds:
                    m.fit_bounds(bounds)
            else:
                st.warning("No geographic data found for selected filters")
        else:
            st.error(f"Could not load geographic data for {region_to_load}")

# Render map - FULL WIDTH
st_folium(m, key="map", use_container_width=True, height=650, returned_objects=[])

# -----------------------------
# Turf Chart (BELOW MAP)
# -----------------------------
if show_turf_chart and len(filtered) > 0 and "voters" in filtered.columns:
    # Filter out empty turfs and aggregate
    turf_filtered = filtered[filtered["Current Turf"] != ""].copy()
    
    if len(turf_filtered) > 0:
        turf_data = (
            turf_filtered
            .groupby("Current Turf", as_index=False)["voters"]
            .sum()
            .sort_values("Current Turf", ascending=True)
        )
        
        # Color palette
        unique_turfs = sorted(turf_data["Current Turf"].unique())
        palette = [
            '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
            '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
            '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
            '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3'
        ]
        turf_colors = {t: palette[i % len(palette)] for i, t in enumerate(unique_turfs)}
        
        fig_turf = px.bar(
            turf_data, 
            x="Current Turf", 
            y="voters",
            color="Current Turf",
            color_discrete_map=turf_colors,
            title="Voter Distribution by Turf",
            height=420
        )
        fig_turf.update_layout(
            xaxis_tickangle=-45,
            xaxis_title="Turf",
            yaxis_title="Voters",
            showlegend=False
        )
        st.plotly_chart(fig_turf, use_container_width=True)

# -----------------------------
# Precinct Chart (BELOW MAP AND TURF CHART)
# -----------------------------
if show_precinct_chart and len(filtered) > 0 and "voters" in filtered.columns:
    # First, aggregate by precinct to avoid duplicate bars
    precinct_data = (
        filtered[filtered["Current Turf"] != ""]
        .groupby(["van_precinct_name", "Current Turf"], as_index=False)["voters"]
        .sum()
        .sort_values(["Current Turf", "van_precinct_name"])
    )
    precinct_data["display_name"] = precinct_data["van_precinct_name"]
    
    if len(precinct_data) > 0:
        # Use same color scheme
        unique_turfs = sorted(precinct_data["Current Turf"].unique())
        palette = [
            '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
            '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
            '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
            '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3'
        ]
        turf_colors = {t: palette[i % len(palette)] for i, t in enumerate(unique_turfs)}
        
        fig_precinct = px.bar(
            precinct_data, 
            x="display_name", 
            y="voters",
            color="Current Turf",
            color_discrete_map=turf_colors,
            title="Voter Distribution by Precinct",
            height=420
        )
        fig_precinct.update_layout(
            xaxis_tickangle=-45,
            xaxis_title="Precinct",
            yaxis_title="Voters",
            showlegend=True
        )
        st.plotly_chart(fig_precinct, use_container_width=True)

# -----------------------------
# Data Table
# -----------------------------
with st.expander("View Data Table"):
    display_cols = ["van_precinct_name", "van_precinct_id", "Current Region", "Current Turf"]
    if "voters" in filtered.columns:
        display_cols.append("voters")
    if "supporters" in filtered.columns:
        display_cols.append("supporters")
    
    available_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(
        filtered[available_cols].sort_values(["Current Turf", "van_precinct_name"]),
        use_container_width=True,
        hide_index=True
    )
    
    csv = filtered[available_cols].to_csv(index=False)
    st.download_button(
        "Download as CSV",
        csv,
        f"turf_data_{selected_region.replace(' ', '_')}.csv",
        "text/csv"
    )
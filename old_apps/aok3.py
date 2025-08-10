import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
from pathlib import Path

st.set_page_config(page_title="Turf Comparison (Original vs Updated)", layout="wide")
st.title("Turf Comparison — Original vs Updated")

# -----------------------------
# Data loaders (cache busts on file mtime so updates show)
# -----------------------------
@st.cache_data
def load_metrics(path, mtime):
    df = pd.read_csv(path)
    df["van_precinct_id"] = df["van_precinct_id"].astype(str)
    return df

@st.cache_data
def load_geojson(path, mtime):
    with open(path, "r") as f:
        data = json.load(f)
    for feature in data["features"]:
        feature["properties"]["van_precinct_id"] = str(feature["properties"]["van_precinct_id"])
    return data

# Paths
METRICS_ORIG = "output/precincts_metrics.csv"
GEOJSON_ORIG = "output/precincts_simplified.geojson"
METRICS_UPD  = "output/precincts_metrics_updated.csv"
GEOJSON_UPD  = "output/precincts_simplified_updated.geojson"

# Load both versions (mtime included -> cache refreshes when files change)
df_orig = load_metrics(METRICS_ORIG, Path(METRICS_ORIG).stat().st_mtime_ns)
geo_orig = load_geojson(GEOJSON_ORIG, Path(GEOJSON_ORIG).stat().st_mtime_ns)
df_upd  = load_metrics(METRICS_UPD,  Path(METRICS_UPD).stat().st_mtime_ns)
geo_upd = load_geojson(GEOJSON_UPD,  Path(GEOJSON_UPD).stat().st_mtime_ns)

# -----------------------------
# QUICK VIEW 
# -----------------------------
QUICK_VIEWS = {
    "": {  # Default empty selection
        "regions": [],
        "turfs": [],
        "desc": ""
    },
    "R07 changes": {
        "regions": ["R07 - South Richmond", "R11 - Southside", "R06 - North Richmond"],
        "turfs": ["R07F - Placeholder3", "R07D - Placeholder2",
                  "R11E - Colonial Heights / Chesterfield", "R07E - North Chesterfield"],
        "desc": "Created new R07F out of pieces from R11E and R07E; moved R06F Rockett's Landing into R07D."
    },
    "R09 split": {
        "regions": ["R09 - Suffolk"],
        "turfs": ["R09F - South", "R09A - Chesapeake", "R09E - Portsmouth"],
        "desc": "Split Portsmouth by taking precincts from Chesapeake and Portsmouth to create R09F."
    },
    "R10 redistribution": {
        "regions": ["R10 - Virginia Beach / Norfolk"],
        "turfs": ["R10F - North", "R10B - Chesapeake", "R10H - Portsmouth",
                  "R10D - Norfolk", "R10E - Norfolk Central", "R10G - North Norfolk", "R10J - West Norfolk"],
        "desc": "Removed R10B and R10H as standalone turfs and redistributed North Norfolk precincts."
    }
}

# Initialize session state for tracking manual changes
if "manual_filter_change" not in st.session_state:
    st.session_state.manual_filter_change = False
if "last_quick_view" not in st.session_state:
    st.session_state.last_quick_view = ""

# Quick view section with left-aligned layout
st.markdown("### Quick Views")
st.markdown("Jump to filters showing the biggest turf changes")

# Create columns for better layout control
col1, col2, col3 = st.columns([2, 3, 3])

with col1:
    # Reset to blank if manual filter change detected
    if st.session_state.manual_filter_change:
        default_index = 0
        st.session_state.manual_filter_change = False
        st.session_state.last_quick_view = ""
    else:
        default_index = 0
    
    # Selector - auto-applies on change
    qv = st.selectbox(
        "Select a view:",
        list(QUICK_VIEWS.keys()),
        index=default_index,
        key="quick_view_selector"
    )
    
    # Track the current quick view
    st.session_state.last_quick_view = qv

# Show description if a view is selected
if qv and QUICK_VIEWS[qv]["desc"]:
    with col2:
        st.info(f"**Changes:** {QUICK_VIEWS[qv]['desc']}")

st.markdown("---")

# Get selected regions and turfs from quick view
if qv:
    default_regions = QUICK_VIEWS[qv]["regions"]
    default_turfs = QUICK_VIEWS[qv]["turfs"]
else:
    default_regions = []
    default_turfs = []

# Callback functions to detect manual changes
def on_region_change():
    if st.session_state.regions_ms != QUICK_VIEWS.get(st.session_state.last_quick_view, {}).get("regions", []):
        st.session_state.manual_filter_change = True

def on_turf_change():
    expected_turfs = QUICK_VIEWS.get(st.session_state.last_quick_view, {}).get("turfs", [])
    # Filter expected turfs to only those available
    if "available_turfs_list" in st.session_state:
        expected_turfs = [t for t in expected_turfs if t in st.session_state.available_turfs_list]
    if st.session_state.turfs_ms != expected_turfs:
        st.session_state.manual_filter_change = True

# -----------------------------
# Sidebar: Filters
# -----------------------------
with st.sidebar:
    st.header("Filters")

    # Regions: union across both versions
    regions = sorted(set(df_orig["Current Region"].dropna().unique())
                     .union(set(df_upd["Current Region"].dropna().unique())))
    regions_with_all = ["VA All Regions"] + regions

    # Regions widget with default from quick view
    selected_regions_raw = st.multiselect(
        "Select Region(s):", 
        regions_with_all, 
        default=default_regions,
        key="regions_ms",
        on_change=on_region_change
    )

    if "VA All Regions" in selected_regions_raw:
        selected_regions = regions
    else:
        selected_regions = [r for r in selected_regions_raw if r != "VA All Regions"]

    # Turfs: union from both versions but limited to selected regions
    if selected_regions:
        turfs_orig = set(df_orig[df_orig["Current Region"].isin(selected_regions)]["Current Turf"].dropna().unique())
        turfs_upd  = set(df_upd [df_upd ["Current Region"].isin(selected_regions)]["Current Turf"].dropna().unique())
        turfs_all  = sorted(turfs_orig.union(turfs_upd))
    else:
        turfs_all = []
    
    # Store available turfs in session state for the callback
    st.session_state.available_turfs_list = turfs_all

    # Turfs widget with default from quick view
    # Only set default turfs if they're in the available turfs
    available_default_turfs = [t for t in default_turfs if t in turfs_all]
    selected_turfs = st.multiselect(
        "Select Turf(s):", 
        turfs_all, 
        default=available_default_turfs,
        key="turfs_ms",
        on_change=on_turf_change
    )

    st.markdown("---")
    show_labels = st.checkbox("Show precinct labels on maps", value=False)

# -----------------------------
# Helper: filter by current selection
# -----------------------------
def filter_df(df):
    if not selected_regions:
        return df.iloc[0:0].copy()
    out = df[df["Current Region"].isin(selected_regions)].copy()
    if selected_turfs:
        out = out[out["Current Turf"].isin(selected_turfs)]
    return out

filtered_orig = filter_df(df_orig)
filtered_upd  = filter_df(df_upd)

# -----------------------------
# KPI row (Updated side as reference)
# -----------------------------
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Precincts (Updated filter)", f"{len(filtered_upd):,}")
with c2:
    st.metric("Voters (Updated filter)",
              f"{int(filtered_upd['voters'].sum()):,}" if "voters" in filtered_upd.columns else "0")
with c3:
    if {"supporters", "voters"}.issubset(filtered_upd.columns) and filtered_upd["voters"].sum() > 0:
        st.metric("Support Rate (Updated filter)",
                  f"{(filtered_upd['supporters'].sum()/filtered_upd['voters'].sum()):.1%}")
    else:
        st.metric("Support Rate (Updated filter)", "N/A")

st.markdown("---")

# -----------------------------
# Palette helper
# -----------------------------
PALETTE = [
    "#e41a1c","#377eb8","#4daf4a","#984ea3","#ff7f00",
    "#ffff33","#a65628","#f781bf","#999999","#66c2a5",
    "#fc8d62","#8da0cb","#e78ac3","#a6d854","#ffd92f",
    "#e5c494","#b3b3b3","#1b9e77","#d95f02","#7570b3",
]
def turf_colors(df):
    turfs = sorted(df["Current Turf"].dropna().unique()) if len(df) else []
    return {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(turfs)}

# -----------------------------
# Two columns: Original vs Updated
# -----------------------------
def render_side(title, df_filt, geo, key_prefix):
    st.subheader(title)

    colors_map = turf_colors(df_filt)

    # Map
    m = folium.Map(location=[37.5407, -77.4360], zoom_start=7, prefer_canvas=True)
    filtered_features = []
    if len(df_filt) > 0:
        selected_ids = set(df_filt["van_precinct_id"])
        filtered_features = [f for f in geo["features"]
                             if f["properties"]["van_precinct_id"] in selected_ids]

        if filtered_features and {"min_lat","min_lon","max_lat","max_lon"}.issubset(df_filt.columns):
            bounds = [
                [df_filt["min_lat"].min(), df_filt["min_lon"].min()],
                [df_filt["max_lat"].max(), df_filt["max_lon"].max()]
            ]
            m.fit_bounds(bounds)

        if filtered_features:
            fc = {"type": "FeatureCollection", "features": filtered_features}
            folium.GeoJson(
                fc,
                style_function=lambda x: {
                    "fillColor": colors_map.get(x["properties"].get("Current Turf"), "#3388ff"),
                    "color": "#000",
                    "weight": 0.5,
                    "fillOpacity": 0.6,
                },
                tooltip=folium.GeoJsonTooltip(   # ALWAYS ON
                    fields=[
                        "van_precinct_name", "van_precinct_id", "county_name",
                        "Current Region", "Current Turf",
                        *(["voters"] if "voters" in df_filt.columns else []),
                        *(["supporters"] if "supporters" in df_filt.columns else []),
                    ],
                    aliases=[
                        "Precinct Name:", "Precinct ID:", "County:",
                        "Region:", "Turf:",
                        *(["Voters:"] if "voters" in df_filt.columns else []),
                        *(["Supporters:"] if "supporters" in df_filt.columns else []),
                    ],
                    localize=True,
                ),
                name="Precincts"
            ).add_to(m)

    if show_labels and len(filtered_features) > 0:
        for feature in filtered_features:
            props = feature["properties"]
            lat, lon = props.get("centroid_lat"), props.get("centroid_lon")
            name = props.get("van_precinct_name", "Unnamed")
            if lat is not None and lon is not None:
                folium.Marker(
                    location=[lat, lon],
                    icon=folium.DivIcon(html=f"""<div style="font-size:10px; color:black; text-align:center;">{name}</div>"""),
                ).add_to(m)

    st_folium(m, key=f"{key_prefix}_map", width=None, height=520, returned_objects=[])

    # Precincts table
    st.markdown("**Precincts in selection**")
    if len(df_filt) > 0:
        cols = [
            "Current Turf", "van_precinct_name", "van_precinct_id", "county_name",
            *(["voters"] if "voters" in df_filt.columns else []),
            *(["supporters"] if "supporters" in df_filt.columns else []),
        ]
        precinct_table = (
            df_filt[cols]
            .sort_values(["Current Turf", "van_precinct_name"], ascending=[True, True])
            .reset_index(drop=True)
        )
        st.dataframe(precinct_table, use_container_width=True, hide_index=True)
        st.download_button(
            "Download table as CSV",
            data=precinct_table.to_csv(index=False),
            file_name=f"{key_prefix}_precincts_in_selection.csv",
            mime="text/csv",
            use_container_width=False,
            key=f"{key_prefix}_dl_precincts"
        )
    else:
        st.info("No precincts in current selection.")

    st.markdown("—")  # small divider

    # Breakdown by Turf table
    st.markdown("**Breakdown by Turf**")
    if len(df_filt) > 0:
        turf_summary = (
            df_filt.groupby("Current Turf")
            .agg(
                voters=("voters", "sum") if "voters" in df_filt.columns else ("van_precinct_id", "size"),
                supporters=("supporters", "sum") if "supporters" in df_filt.columns else ("van_precinct_id", "size"),
                precinct_count=("van_precinct_id", "count"),
            )
            .sort_index()
        )
        st.dataframe(turf_summary, use_container_width=True)
        st.download_button(
            "Download breakdown as CSV",
            data=turf_summary.reset_index().to_csv(index=False),
            file_name=f"{key_prefix}_breakdown_by_turf.csv",
            mime="text/csv",
            use_container_width=False,
            key=f"{key_prefix}_dl_breakdown"
        )
    else:
        st.info("No turf breakdown for current selection.")

col_left, col_right = st.columns(2, gap="large")
with col_left:
    render_side("Original Turfs", filtered_orig, geo_orig, key_prefix="orig")
with col_right:
    render_side("Updated Turfs", filtered_upd, geo_upd, key_prefix="upd")
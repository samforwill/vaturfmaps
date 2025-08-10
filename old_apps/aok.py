import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json

st.set_page_config(page_title="Turf Comparison (Original vs Updated)", layout="wide")
st.title("Turf Comparison — Original vs Updated")

# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data
def load_metrics(path):
    df = pd.read_csv(path)
    df["van_precinct_id"] = df["van_precinct_id"].astype(str)
    return df

@st.cache_data
def load_geojson(path):
    with open(path, "r") as f:
        data = json.load(f)
    for feature in data["features"]:
        feature["properties"]["van_precinct_id"] = str(feature["properties"]["van_precinct_id"])
    return data

# Paths
METRICS_ORIG = "output/precincts_metrics.csv"
GEOJSON_ORIG = "output/precincts_simplified.geojson"

METRICS_UPD = "output/precincts_metrics_updated.csv"
GEOJSON_UPD = "output/precincts_simplified_updated.geojson"

# Load both versions
df_orig = load_metrics(METRICS_ORIG)
geo_orig = load_geojson(GEOJSON_ORIG)

df_upd = load_metrics(METRICS_UPD)
geo_upd = load_geojson(GEOJSON_UPD)

# -----------------------------
# Sidebar: shared filters + options
# -----------------------------
with st.sidebar:
    st.header("Filters")

    # Regions: union across both versions
    regions = sorted(set(df_orig["Current Region"].dropna().unique()).union(
                     set(df_upd["Current Region"].dropna().unique())))
    regions_with_all = ["VA All Regions"] + regions

    selected_regions_raw = st.multiselect(
        "Select Region(s):",
        regions_with_all,
        default=[]  # default to full state
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
        selected_turfs = st.multiselect("Select Turf(s):", turfs_all, default=[])
    else:
        selected_turfs = []

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
# KPI row (from UPDATED view, but you can change to show both if you want)
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
# Palette helper per side
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
# Two columns: Original (left) vs Updated (right)
# -----------------------------
col_left, col_right = st.columns(2, gap="large")

def render_side(title, df_filt, geo, key_prefix):
    st.subheader(title)

    # Colors
    colors_map = turf_colors(df_filt)

    # Map
    m = folium.Map(location=[37.5407, -77.4360], zoom_start=7, prefer_canvas=True)

    filtered_features = []
    if len(df_filt) > 0:
        selected_ids = set(df_filt["van_precinct_id"])
        filtered_features = [f for f in geo["features"]
                             if f["properties"]["van_precinct_id"] in selected_ids]

        # Fit bounds if we have precomputed bounds in df
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
                tooltip=folium.GeoJsonTooltip(
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
                ) if len(filtered_features) < 1000 else None,
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
                    icon=folium.DivIcon(
                        html=f"""<div style="font-size:10px; color:black; text-align:center;">{name}</div>"""
                    ),
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

with col_left:
    render_side("Original", filtered_orig, geo_orig, key_prefix="orig")

with col_right:
    render_side("Updated Turfs", filtered_upd, geo_upd, key_prefix="upd")

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
from datetime import datetime
from pathlib import Path
import plotly.express as px
from shapely import wkt
from shapely.geometry import mapping
from folium.plugins import Search


st.set_page_config(page_title="Turf Viewer", layout="wide")
st.title("Turf Map Viewer")

DATA_DIR = Path("output")
METRICS_CSV = DATA_DIR / "precincts_metrics_updated.csv"
GEOJSON_ALL = DATA_DIR / "precincts_simplified_updated.geojson"
REGION_DIR = DATA_DIR / "regions"  # per-region *_updated.geojson
STATE_TARGETS_CSV = DATA_DIR / "target_districts.csv"  # statewide targets
# Per-region targets like output/R03_target_districts.csv

# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data
def load_metrics():
    df = pd.read_csv(METRICS_CSV)
    df["van_precinct_id"] = df["van_precinct_id"].astype(str)
    if {"supporters", "voters"}.issubset(df.columns):
        df["support_rate"] = (df["supporters"] / df["voters"]).fillna(0.0).round(3)
    return df

@st.cache_data
def load_geojson_all():
    with open(GEOJSON_ALL, "r") as f:
        data = json.load(f)
    for feat in data["features"]:
        feat["properties"]["van_precinct_id"] = str(feat["properties"]["van_precinct_id"])
    return data

@st.cache_data
def load_geojson_region(region_name: str):
    safe = region_name.replace("/", "_").replace(" ", "_")
    path = REGION_DIR / f"{safe}_updated.geojson"
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
        for feat in data["features"]:
            feat["properties"]["van_precinct_id"] = str(feat["properties"]["van_precinct_id"])
        return data
    return load_geojson_all()

@st.cache_data
def load_target_csv(path: Path):
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    df_t = pd.read_csv(path)
    if "WKT" not in df_t.columns or df_t["WKT"].isna().all():
        return {"type": "FeatureCollection", "features": []}
    df_t = df_t.copy()
    df_t["__geom__"] = df_t["WKT"].apply(lambda s: wkt.loads(s) if isinstance(s, str) else None)
    features = []
    prop_cols = [c for c in df_t.columns if c not in {"WKT", "__geom__"}]
    for _, row in df_t.iterrows():
        geom = row["__geom__"]
        if geom is None:
            continue
        props = {c: row[c] for c in prop_cols}
        features.append({"type": "Feature", "geometry": mapping(geom), "properties": props})
    return {"type": "FeatureCollection", "features": features}

@st.cache_data
def load_targets_for_selection(statewide: bool, regions_selected: list[str]):
    if statewide:
        return load_target_csv(STATE_TARGETS_CSV)
    all_feats = []
    for r in regions_selected:
        path = DATA_DIR / f"{r}_target_districts.csv"
        fc = load_target_csv(path)
        if fc.get("features"):
            all_feats.extend(fc["features"])
    return {"type": "FeatureCollection", "features": all_feats}

# -----------------------------
# Load core data
# -----------------------------
df = load_metrics()

# -----------------------------
# Sidebar filters and download
# -----------------------------
with st.sidebar:
    st.header("Filters")

    regions = sorted(df["Current Region"].dropna().unique())
    regions_with_all = ["VA All Regions"] + regions

    # Default statewide
    picked_regions_raw = st.multiselect("Select Region(s)", regions_with_all, default=["VA All Regions"])

    # If any specific region chosen, drop All
    picked_specific = [r for r in picked_regions_raw if r != "VA All Regions"]
    statewide = len(picked_specific) == 0  # true if only All or nothing

    if statewide:
        active_regions = regions[:]  # all regions
    else:
        active_regions = picked_specific

    if active_regions:
        available_turfs = sorted(df[df["Current Region"].isin(active_regions)]["Current Turf"].dropna().unique())
        picked_turfs = st.multiselect("Select Turf(s)", available_turfs, default=[])
    else:
        picked_turfs = []

    show_labels = st.checkbox("Show precinct labels", value=False)
    show_targets = st.checkbox("Show Targeted House Districts", value=False)

# Build filtered df exactly once
filtered = df[df["Current Region"].isin(active_regions)]
if picked_turfs:
    filtered = filtered[filtered["Current Turf"].isin(picked_turfs)]

# Download in sidebar
with st.sidebar:
    st.download_button(
        "Download filtered CSV",
        data=filtered.to_csv(index=False),
        file_name=f"filtered_precincts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True
    )

# -----------------------------
# KPIs
# -----------------------------
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Precincts", f"{len(filtered):,}")
with col2:
    st.metric("Voters", f"{int(filtered['voters'].sum()):,}" if "voters" in filtered.columns else "N/A")
with col3:
    if {"supporters", "voters"}.issubset(filtered.columns) and filtered["voters"].sum() > 0:
        st.metric("Support rate", f"{(filtered['supporters'].sum()/filtered['voters'].sum()):.1%}")
    else:
        st.metric("Support rate", "N/A")


# -----------------------------
# Map
# -----------------------------
m = folium.Map(location=[37.5407, -77.4360], zoom_start=7, prefer_canvas=True)

filtered_features = []
if len(filtered) > 0:
    selected_ids = set(filtered["van_precinct_id"].astype(str))
    # Load only the regions we need
    region_geojsons = [load_geojson_region(r) for r in sorted(set(filtered["Current Region"]))]

    for gj in region_geojsons:
        for f in gj["features"]:
            if f["properties"]["van_precinct_id"] in selected_ids:
                filtered_features.append(f)

    if filtered_features and {"min_lat", "min_lon", "max_lat", "max_lon"}.issubset(filtered.columns):
        bounds = [
            [filtered["min_lat"].min(), filtered["min_lon"].min()],
            [filtered["max_lat"].max(), filtered["max_lon"].max()],
        ]
        m.fit_bounds(bounds)

    if filtered_features:
        unique_turfs = sorted({f["properties"].get("Current Turf", "") for f in filtered_features})
        palette = [
            '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
            '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
            '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
            '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3'
        ]
        turf_colors = {t: palette[i % len(palette)] for i, t in enumerate(unique_turfs)}

        for f in filtered_features:
            p = f["properties"]
        p["search_key"] = f"{p.get('van_precinct_name','')} {p.get('van_precinct_id','')}"

        filtered_geojson = {"type": "FeatureCollection", "features": filtered_features}
        precinct_layer = folium.GeoJson(
            filtered_geojson,
            style_function=lambda x: {
                "fillColor": turf_colors.get(x["properties"].get("Current Turf", ""), "#3388ff"),
                "color": "#000",
                "weight": 0.5,
                "fillOpacity": 0.6,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[
                    "van_precinct_name", "van_precinct_id", "county_name",
                    "Current Region", "Current Turf",
                    *(["voters"] if "voters" in df.columns else []),
                    *(["supporters"] if "supporters" in df.columns else []),
                ],
                aliases=[
                    "Precinct Name:", "Precinct ID:", "County:",
                    "Region:", "Turf:",
                    *(["Voters:"] if "voters" in df.columns else []),
                    *(["Supporters:"] if "supporters" in df.columns else []),
                ],
                localize=True,
            ) if len(filtered_features) < 1000 else None,
            name="Precincts"
        ).add_to(m)

        Search(
            layer=precinct_layer,
            search_label="search_key",          # searches both name + id
            placeholder="Search precinct…",
            collapsed=False,
            position="topleft"
        ).add_to(m)

        if show_labels:
            for feat in filtered_features:
                props = feat["properties"]
                lat = props.get("centroid_lat")
                lon = props.get("centroid_lon")
                name = props.get("van_precinct_name", "Unnamed")
                if lat is not None and lon is not None:
                    folium.Marker(
                        location=[lat, lon],
                        icon=folium.DivIcon(
                            html=f"""<div style="font-size:10px; color:black; text-align:center;">{name}</div>"""
                        ),
                    ).add_to(m)

# Targeted House Districts overlay
if show_targets:
    targets_fc = load_targets_for_selection(statewide=statewide, regions_selected=active_regions)
    if targets_fc.get("features"):
        # Build tooltip fields dynamically
        sample_props = list(targets_fc["features"][0].get("properties", {}).keys()) if targets_fc["features"] else []
        tooltip_fields = [c for c in sample_props]
        tooltip_aliases = [f"{c}:" for c in tooltip_fields]

        folium.GeoJson(
            targets_fc,
            style_function=lambda x: {
                "fillColor": "#ff0000",
                "color": "#ff0000",
                "weight": 2,
                "fillOpacity": 0.12,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=tooltip_aliases,
                localize=True,
            ) if tooltip_fields else None,
            name="Targeted House Districts",
        ).add_to(m)

        folium.LayerControl(collapsed=True).add_to(m)

st_folium(m, key="map", width=None, height=650, returned_objects=[])
# -----------------------------
# New chart: compare turfs (only if >1 turf)
# -----------------------------
show_turfs = st.checkbox("Show voters by turf", value=False, key="show_turfs_chart")

if show_turfs and len(filtered) > 0 and filtered["Current Turf"].nunique() > 1:

    # Chart 1: Voters by Turf
    agg_turfs = (
        filtered.groupby("Current Turf", as_index=False)["voters"]
        .sum()
        .sort_values("voters", ascending=False)
    )
    fig_turfs = px.bar(
        agg_turfs, x="Current Turf", y="voters",
        title="Voters by Turf in Current Filter", height=420
    )
    fig_turfs.update_layout(xaxis_title="Turf", yaxis_title="Voters",
                            xaxis={'categoryorder':'total descending'})
    st.plotly_chart(fig_turfs, use_container_width=True)

    # Chart 2: Support Rate by Turf (only if data is available)
    if {"supporters", "voters"}.issubset(filtered.columns):
        agg_sr = filtered.groupby("Current Turf", as_index=False)[["supporters","voters"]].sum()
        agg_sr = agg_sr[agg_sr["voters"] > 0].copy()
        agg_sr["support_rate"] = agg_sr["supporters"] / agg_sr["voters"]
        fig_sr = px.bar(
            agg_sr.sort_values("support_rate", ascending=False),
            x="Current Turf", y="support_rate",
            title="Support Rate by Turf", height=420
        )
        fig_sr.update_layout(xaxis_title="Turf", yaxis_title="Support rate")
        st.plotly_chart(fig_sr, use_container_width=True)



# -----------------------------
# Original precinct chart(s) below the map
# -----------------------------
if len(filtered) > 0:
    show_hist = st.checkbox("Show voter distribution by precinct", value=False, key="show_precincts_chart")
    if show_hist and "voters" in filtered.columns:
        # Chart 1: Voters by Precinct
        hist_df = filtered.sort_values(["Current Turf", "van_precinct_name"]).copy()
        hist_df["display_name"] = hist_df["van_precinct_name"]
        fig3 = px.bar(
            hist_df, x="display_name", y="voters",
            color="Current Turf",
            title="Voter Distribution by Precinct",
            height=420
        )
        fig3.update_layout(
            xaxis_tickangle=-45,
            xaxis_title="Precinct",
            yaxis_title="Voters",
            xaxis={'categoryorder':'total descending'}
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Chart 2: Support Rate by Precinct (only if data available)
        if {"supporters", "voters"}.issubset(filtered.columns):
            sr_df = hist_df.groupby(["display_name", "Current Turf"], as_index=False)[["supporters","voters"]].sum()
            sr_df = sr_df[sr_df["voters"] > 0].copy()
            sr_df["support_rate"] = sr_df["supporters"] / sr_df["voters"]
            fig_sr = px.bar(
                sr_df.sort_values("support_rate", ascending=False),
                x="display_name", y="support_rate",
                color="Current Turf",
                title="Support Rate by Precinct",
                height=420
            )
            fig_sr.update_layout(
                xaxis_tickangle=-45,
                xaxis_title="Precinct",
                yaxis_title="Support rate"
            )
            st.plotly_chart(fig_sr, use_container_width=True)

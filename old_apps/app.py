import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json

st.set_page_config(page_title="Turf Map", layout="wide")
st.title("Turf Mapping")

# Load preprocessed data - FAST!
@st.cache_data
def load_metrics():
    """Load just the metrics for filtering - no geometry parsing needed"""
    df = pd.read_csv("output/precincts_metrics.csv")
    # Ensure van_precinct_id is string type
    df['van_precinct_id'] = df['van_precinct_id'].astype(str)
    return df

@st.cache_data
def load_geojson():
    """Load preprocessed GeoJSON - already simplified"""
    with open('output/precincts_simplified.geojson', 'r') as f:
        data = json.load(f)
        # Ensure van_precinct_id is string in GeoJSON properties too
        for feature in data['features']:
            feature['properties']['van_precinct_id'] = str(feature['properties']['van_precinct_id'])
        return data

# Load data
df_metrics = load_metrics()
geojson_data = load_geojson()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    
    # Add "All Regions" option to the list
    regions = sorted(df_metrics['Current Region'].unique())
    regions_with_all = ["VA All Regions"] + regions
    
    # Region multiselect with "All Regions" option
    selected_regions_raw = st.multiselect(
        "Select Region(s):", 
        regions_with_all,
        default=[]
    )
    
    # Handle "VA All Regions" selection
    if "VA All Regions" in selected_regions_raw:
        selected_regions = regions  # Select all actual regions
    else:
        selected_regions = [r for r in selected_regions_raw if r != "VA All Regions"]
    
    # Turf multiselect (only show if regions selected)
    if selected_regions:
        available_turfs = sorted(
            df_metrics[df_metrics['Current Region'].isin(selected_regions)]['Current Turf'].unique()
        )
        selected_turfs = st.multiselect(
            "Select Turf(s):", 
            available_turfs,
            default=[]
        )
    else:
        selected_turfs = []

# Filter the metrics data
if selected_regions:
    filtered_metrics = df_metrics[df_metrics['Current Region'].isin(selected_regions)]
    if selected_turfs:
        filtered_metrics = filtered_metrics[filtered_metrics['Current Turf'].isin(selected_turfs)]
else:
    filtered_metrics = pd.DataFrame()  # Empty if nothing selected

# Display summary metrics at the top
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Precincts", f"{len(filtered_metrics):,}")
with col2:
    st.metric("Total Voters", f"{filtered_metrics['voters'].sum():,}" if len(filtered_metrics) > 0 else "0")
with col3:
    st.metric("Total Supporters", f"{filtered_metrics['supporters'].sum():,}" if len(filtered_metrics) > 0 else "0")

# Create map - starts with empty map of Virginia
# Richmond, VA coordinates as default center
m = folium.Map(
    location=[37.5407, -77.4360],  # Richmond, VA
    zoom_start=7,  # State-level zoom
    prefer_canvas=True,  # Faster rendering
)

# Only add geometries if something is selected
if len(filtered_metrics) > 0:
    # Get the van_precinct_ids to display
    selected_ids = set(filtered_metrics['van_precinct_id'])  # Already strings now
    
    # Filter GeoJSON features to only show selected precincts
    filtered_features = [
        f for f in geojson_data['features'] 
        if f['properties']['van_precinct_id'] in selected_ids
    ]
    
    if filtered_features:
        # Auto-zoom to fit selected data
        bounds = [
            [filtered_metrics['min_lat'].min(), filtered_metrics['min_lon'].min()],
            [filtered_metrics['max_lat'].max(), filtered_metrics['max_lon'].max()]
        ]
        m.fit_bounds(bounds)
        
        # Create color map for turfs
        unique_turfs = list(set(f['properties']['Current Turf'] for f in filtered_features))
        colors = ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
                 '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
                 '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
                 '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3']
        
        # Create turf to color mapping
        turf_colors = {turf: colors[i % len(colors)] for i, turf in enumerate(unique_turfs)}
        
        # Create filtered GeoJSON collection
        filtered_geojson = {
            "type": "FeatureCollection",
            "features": filtered_features
        }
        
        # Add all precincts as a single GeoJSON layer with turf-based coloring
        folium.GeoJson(
            filtered_geojson,
            style_function=lambda x: {
                'fillColor': turf_colors.get(x['properties']['Current Turf'], '#3388ff'),
                'color': '#000',
                'weight': 0.5,
                'fillOpacity': 0.6
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['van_precinct_name', 'van_precinct_id', 'county_name', 'Current Region', 'Current Turf', 'voters', 'supporters'],
                aliases=['Precinct Name:', 'Precinct ID:', 'County:', 'Region:', 'Turf:', 'Voters:', 'Supporters:'],
                localize=True
            ) if len(filtered_features) < 1000 else None  # Disable tooltips for performance on large datasets
        ).add_to(m)

# Display map (empty or with data)
st_folium(m, key="map", width=None, height=600, returned_objects=[])

# Optional: Show summary by turf
if len(filtered_metrics) > 0:
    if st.checkbox("Show breakdown by turf"):
        turf_summary = filtered_metrics.groupby('Current Turf').agg({
            'voters': 'sum',
            'supporters': 'sum',
            'van_precinct_id': 'count'
        }).rename(columns={'van_precinct_id': 'precinct_count'}).sort_values('voters', ascending=False)
        
        st.dataframe(turf_summary, use_container_width=True)

# Debug info (can remove in production)
with st.expander("Debug Info"):
    st.write(f"Total precincts in dataset: {len(df_metrics):,}")
    st.write(f"Selected regions: {selected_regions}")
    st.write(f"Selected turfs: {selected_turfs}")
    if len(filtered_metrics) > 0:
        st.write(f"Filtered precincts: {len(filtered_metrics):,}")
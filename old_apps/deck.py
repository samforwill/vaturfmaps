import streamlit as st
import pandas as pd
import pydeck as pdk
import json

st.set_page_config(page_title="Turf Map", layout="wide")
st.title("Turf Mapping")

# Set Mapbox token as environment variable (pydeck prefers this)
import os
os.environ['MAPBOX_API_KEY'] = "pk.eyJ1Ijoic2FtZm9yd2lsbCIsImEiOiJjbWUxcmU3aGUwamptMnNwdjJmNGM5OHV0In0.Q-yLWqRDqwjRD3L1CX-uCg"

# Load preprocessed data
@st.cache_data
def load_metrics():
    """Load just the metrics for filtering - no geometry parsing needed"""
    df = pd.read_csv("output/precincts_metrics.csv")
    df['van_precinct_id'] = df['van_precinct_id'].astype(str)
    return df

@st.cache_data
def load_geojson():
    """Load preprocessed GeoJSON - already simplified"""
    with open('output/precincts_simplified.geojson', 'r') as f:
        data = json.load(f)
        for feature in data['features']:
            feature['properties']['van_precinct_id'] = str(feature['properties']['van_precinct_id'])
        return data

# Load data
df_metrics = load_metrics()
geojson_data = load_geojson()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    
    # Add "All Regions" option
    regions = sorted(df_metrics['Current Region'].unique())
    regions_with_all = ["VA All Regions"] + regions
    
    selected_regions_raw = st.multiselect(
        "Select Region(s):", 
        regions_with_all,
        default=[]
    )
    
    # Handle "VA All Regions" selection
    if "VA All Regions" in selected_regions_raw:
        selected_regions = regions
    else:
        selected_regions = [r for r in selected_regions_raw if r != "VA All Regions"]
    
    # Turf multiselect
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
    filtered_metrics = pd.DataFrame()

# Display summary metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Precincts", f"{len(filtered_metrics):,}")
with col2:
    st.metric("Total Voters", f"{filtered_metrics['voters'].sum():,}" if len(filtered_metrics) > 0 else "0")
with col3:
    st.metric("Total Supporters", f"{filtered_metrics['supporters'].sum():,}" if len(filtered_metrics) > 0 else "0")

# Initialize view state - use session state to preserve position
if 'view_state' not in st.session_state:
    st.session_state.view_state = pdk.ViewState(
        latitude=37.4316,  # Center of Virginia
        longitude=-78.6569,
        zoom=6,
        pitch=0
    )

# Prepare GeoJSON data for the layer
layer_data = {"type": "FeatureCollection", "features": []}

if len(filtered_metrics) > 0:
    # Get selected precinct IDs
    selected_ids = set(filtered_metrics['van_precinct_id'])
    
    # Filter GeoJSON features
    filtered_features = [
        f for f in geojson_data['features'] 
        if f['properties']['van_precinct_id'] in selected_ids
    ]
    
    if filtered_features:
        # Create color map for turfs
        unique_turfs = sorted(list(set(f['properties']['Current Turf'] for f in filtered_features)))
        
        # RGB colors for different turfs
        colors = [
            [228, 26, 28], [55, 126, 184], [77, 175, 74], [152, 78, 163],
            [255, 127, 0], [255, 255, 51], [166, 86, 40], [247, 129, 191],
            [153, 153, 153], [102, 194, 165], [252, 141, 98], [141, 160, 203],
            [231, 138, 195], [166, 216, 84], [255, 217, 47], [229, 196, 148],
            [179, 179, 179], [27, 158, 119], [217, 95, 2], [117, 112, 179]
        ]
        
        turf_colors = {turf: colors[i % len(colors)] for i, turf in enumerate(unique_turfs)}
        
        # Add color and tooltip to each feature
        for feature in filtered_features:
            turf = feature['properties']['Current Turf']
            # Add RGBA color directly to properties
            feature['properties']['fill_color'] = turf_colors[turf] + [180]  # Add alpha
            feature['properties']['line_color'] = [0, 0, 0, 255]
            
        layer_data = {
            "type": "FeatureCollection",
            "features": filtered_features
        }

# Create the layer
geojson_layer = pdk.Layer(
    "GeoJsonLayer",
    data=layer_data,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.fill_color",
    get_line_color="properties.line_color",
    get_line_width=50,  # width in meters
    line_width_min_pixels=0.5,
    auto_highlight=True,
    highlight_color=[255, 255, 0, 128]
)

# Create deck
deck = pdk.Deck(
    layers=[geojson_layer],
    initial_view_state=st.session_state.view_state,
    map_provider="mapbox",
    map_style="mapbox://styles/mapbox/light-v10",
    tooltip={
        "html": "<b>{van_precinct_name}</b><br/>"
                "ID: {van_precinct_id}<br/>"
                "County: {county_name}<br/>"
                "Region: {Current Region}<br/>"
                "Turf: {Current Turf}<br/>"
                "Voters: {voters}<br/>"
                "Supporters: {supporters}",
        "style": {
            "backgroundColor": "steelblue",
            "color": "white"
        }
    }
)

# Render the deck
event = st.pydeck_chart(deck, height=600, use_container_width=True, key="deck_map")

# Try to capture and update view state (experimental)
if event:
    try:
        # This might not work perfectly but worth trying
        if hasattr(event, 'view_state'):
            st.session_state.view_state = event.view_state
    except:
        pass

# Optional: Show summary by turf
if len(filtered_metrics) > 0:
    if st.checkbox("Show breakdown by turf"):
        turf_summary = filtered_metrics.groupby('Current Turf').agg({
            'voters': 'sum',
            'supporters': 'sum',
            'van_precinct_id': 'count'
        }).rename(columns={'van_precinct_id': 'precinct_count'}).sort_values('voters', ascending=False)
        
        st.dataframe(turf_summary, use_container_width=True)

# Debug info
with st.expander("Debug Info"):
    st.write(f"Total precincts in dataset: {len(df_metrics):,}")
    st.write(f"Selected regions: {selected_regions}")
    st.write(f"Selected turfs: {selected_turfs}")
    st.write(f"Filtered precincts: {len(filtered_metrics):,}")
    st.write(f"Features in layer: {len(layer_data.get('features', []))}")
    if len(layer_data.get('features', [])) > 0:
        st.write("Sample feature properties:", layer_data['features'][0]['properties'].keys())
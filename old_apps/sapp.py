import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json

st.set_page_config(page_title="Turf Map", layout="wide")
st.title("Turf Mapping")

# Your Mapbox token
MAPBOX_TOKEN = "pk.eyJ1Ijoic2FtZm9yd2lsbCIsImEiOiJjbWUxcmU3aGUwamptMnNwdjJmNGM5OHV0In0.Q-yLWqRDqwjRD3L1CX-uCg"

# Load preprocessed data
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

# Create Plotly map
fig = go.Figure()

# Use session state to preserve map view between interactions
if 'map_state' not in st.session_state:
    # First load - center on Virginia
    st.session_state.map_state = {
        'center': {'lat': 37.4316, 'lon': -78.6569},
        'zoom': 6.5
    }

# Check if the map state was updated from the last interaction
if 'map' in st.session_state:
    relayout_data = st.session_state.map.get('relayout_data', {})
    if 'mapbox.center' in relayout_data:
        st.session_state.map_state['center'] = relayout_data['mapbox.center']
    if 'mapbox.zoom' in relayout_data:
        st.session_state.map_state['zoom'] = relayout_data['mapbox.zoom']

# Set layout with preserved state
fig.update_layout(
    mapbox=dict(
        accesstoken=MAPBOX_TOKEN,
        style="mapbox://styles/mapbox/light-v10",
        center=st.session_state.map_state['center'],
        zoom=st.session_state.map_state['zoom']
    ),
    margin=dict(l=0, r=0, t=0, b=0),
    height=600,
    showlegend=True,
    legend=dict(
        yanchor="top",
        y=0.99,
        xanchor="left",
        x=0.01,
        bgcolor="rgba(255, 255, 255, 0.8)"
    ),
    dragmode='pan'
)

# Add geometries if something is selected
if len(filtered_metrics) > 0:
    # Get the van_precinct_ids to display
    selected_ids = set(filtered_metrics['van_precinct_id'])
    
    # Filter GeoJSON features
    filtered_features = [
        f for f in geojson_data['features'] 
        if f['properties']['van_precinct_id'] in selected_ids
    ]
    
    if filtered_features:
        # Create filtered GeoJSON
        filtered_geojson = {
            "type": "FeatureCollection",
            "features": filtered_features
        }
        
        # Get unique turfs for coloring
        unique_turfs = sorted(list(set(f['properties']['Current Turf'] for f in filtered_features)))
        
        # Add a choroplethmapbox trace for each turf (for categorical coloring)
        for i, turf in enumerate(unique_turfs):
            # Filter features for this turf
            turf_features = [
                f for f in filtered_features 
                if f['properties']['Current Turf'] == turf
            ]
            
            turf_geojson = {
                "type": "FeatureCollection",
                "features": turf_features
            }
            
            # Create hover text for this turf's precincts
            hover_texts = []
            for feature in turf_features:
                props = feature['properties']
                hover_text = (
                    f"<b>{props.get('van_precinct_name', 'Unknown')}</b><br>"
                    f"Precinct ID: {props.get('van_precinct_id', '')}<br>"
                    f"County: {props.get('county_name', '')}<br>"
                    f"Region: {props.get('Current Region', '')}<br>"
                    f"Turf: {props.get('Current Turf', '')}<br>"
                    f"Voters: {props.get('voters', 0):,}<br>"
                    f"Supporters: {props.get('supporters', 0):,}"
                )
                hover_texts.append(hover_text)
            
            # Add trace for this turf
            fig.add_trace(go.Choroplethmapbox(
                geojson=turf_geojson,
                locations=[f['properties']['van_precinct_id'] for f in turf_features],
                z=[1] * len(turf_features),  # Dummy z values for coloring
                featureidkey="properties.van_precinct_id",
                colorscale=[[0, f"rgba({(i*50)%256}, {(i*80)%256}, {(i*120)%256}, 0.6)"], 
                           [1, f"rgba({(i*50)%256}, {(i*80)%256}, {(i*120)%256}, 0.6)"]],
                showscale=False,
                hovertext=hover_texts,
                hoverinfo="text",
                marker=dict(line=dict(width=0.5, color='black')),
                name=turf
            ))

# Display the map with scroll zoom enabled and capture state
config = {
    'scrollZoom': True,  # Enable scroll to zoom without Ctrl
    'displayModeBar': True,  # Show the toolbar
    'displaylogo': False,  # Remove plotly logo
    'modeBarButtonsToRemove': ['select2d', 'lasso2d']  # Remove unnecessary tools
}

st.plotly_chart(fig, use_container_width=True, key="map", config=config)

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
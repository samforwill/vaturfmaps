import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Turf Map", layout="wide")
st.title("Turf Mapping")

# Initialize session state for tracking changes
if 'master_df' not in st.session_state:
    st.session_state.master_df = None
if 'changed_precincts' not in st.session_state:
    st.session_state.changed_precincts = set()

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

# Initialize master_df in session state if not already done
if st.session_state.master_df is None:
    st.session_state.master_df = df_metrics.copy()

# Use the master_df from session state (includes any previous changes)
df_metrics = st.session_state.master_df.copy()

# Update GeoJSON with current assignments from master_df
for feature in geojson_data['features']:
    precinct_id = feature['properties']['van_precinct_id']
    current_data = df_metrics[df_metrics['van_precinct_id'] == precinct_id]
    if not current_data.empty:
        feature['properties']['Current Region'] = current_data.iloc[0]['Current Region']
        feature['properties']['Current Turf'] = current_data.iloc[0]['Current Turf']

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
    
    # Show count of changed precincts
    if len(st.session_state.changed_precincts) > 0:
        st.sidebar.success(f"{len(st.session_state.changed_precincts)} precincts modified")
    
    # Download button for updated CSV
    if st.sidebar.button("Download Updated CSV", type="secondary", use_container_width=True):
        # Add the Changed column for export
        export_df = st.session_state.master_df.copy()
        export_df['Changed'] = export_df['van_precinct_id'].isin(st.session_state.changed_precincts)
        
        csv = export_df.to_csv(index=False)
        st.sidebar.download_button(
            label="Save CSV",
            data=csv,
            file_name=f"updated_precincts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime='text/csv',
        )

# Filter the metrics data
if selected_regions:
    filtered_metrics = df_metrics[df_metrics['Current Region'].isin(selected_regions)]
    if selected_turfs:
        filtered_metrics = filtered_metrics[filtered_metrics['Current Turf'].isin(selected_turfs)]
else:
    filtered_metrics = pd.DataFrame()  # Empty if nothing selected

# Display summary metrics at the top with connected boxes
with st.container():
    st.markdown("""
        <style>
        [data-testid="metric-container"] {
            background-color: rgba(248, 249, 251, 0.6);
            border: 1px solid rgba(49, 51, 63, 0.2);
            padding: 10px 15px;
            border-radius: 0px;
            margin: 0px;
        }
        [data-testid="metric-container"]:first-child {
            border-radius: 5px 0 0 5px;
        }
        [data-testid="metric-container"]:last-child {
            border-radius: 0 5px 5px 0;
        }
        </style>
        """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Precincts in Filter", f"{len(filtered_metrics):,}")
    with col2:
        st.metric("Total Voters in Filter", f"{filtered_metrics['voters'].sum():,}" if len(filtered_metrics) > 0 else "0")
    with col3:
        st.metric("Total Supporters in Filter", f"{filtered_metrics['supporters'].sum():,}" if len(filtered_metrics) > 0 else "0")
    with col4:
        st.metric("Modified Precincts", f"{len(st.session_state.changed_precincts):,}")

# Create map - starts with empty map of Virginia
# Richmond, VA coordinates as default center
m = folium.Map(
    location=[37.5407, -77.4360],  # Richmond, VA
    zoom_start=7,  # State-level zoom
    prefer_canvas=True,  # Faster rendering
)

# Track turf colors for consistency across map and charts
turf_colors_map = {}

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
        unique_turfs = sorted(list(set(f['properties']['Current Turf'] for f in filtered_features)))
        colors = ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
                 '#ffff33','#a65628','#f781bf','#999999','#66c2a5',
                 '#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f',
                 '#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3']
        
        # Create turf to color mapping and store for use in charts
        turf_colors_map = {turf: colors[i % len(colors)] for i, turf in enumerate(unique_turfs)}
        
        # Create filtered GeoJSON collection
        filtered_geojson = {
            "type": "FeatureCollection",
            "features": filtered_features
        }
        
        # Add all precincts as a single GeoJSON layer with turf-based coloring
        folium.GeoJson(
            filtered_geojson,
            style_function=lambda x: {
                'fillColor': turf_colors_map.get(x['properties']['Current Turf'], '#3388ff'),
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

# Breakdown by Turf Section - Always show
if len(filtered_metrics) > 0:
    st.subheader("Breakdown by Turf")
    
    turf_summary = filtered_metrics.groupby('Current Turf').agg({
        'voters': 'sum',
        'supporters': 'sum',
        'van_precinct_id': 'count'
    }).rename(columns={'van_precinct_id': 'precinct_count'}).sort_index()  # Sort by Current Turf ascending
    
    # Format numbers with commas
    turf_summary['voters'] = turf_summary['voters'].apply(lambda x: f'{x:,}')
    turf_summary['supporters'] = turf_summary['supporters'].apply(lambda x: f'{x:,}')
    
    st.dataframe(turf_summary, use_container_width=True)
    
    # Optional histogram section
    if st.checkbox("Show voter distribution by precinct"):
        # Prepare data for histogram - sort by turf then precinct name
        hist_df = filtered_metrics.sort_values(['Current Turf', 'van_precinct_name']).copy()
        hist_df['display_name'] = hist_df['van_precinct_name']
        hist_df['color'] = hist_df['Current Turf'].map(turf_colors_map)
        
        # Create custom hover data
        hist_df['hover_text'] = (
            hist_df['van_precinct_name'] + '<br>' +
            hist_df['Current Turf'] + '<br>' +
            'Voters: ' + hist_df['voters'].apply(lambda x: f'{x:,}')
        )
        
        # Create plotly bar chart
        fig = px.bar(
            hist_df, 
            x='display_name', 
            y='voters',
            color='Current Turf',
            color_discrete_map=turf_colors_map,
            labels={'display_name': 'Precinct', 'voters': 'Voters'},
            title='Voter Distribution by Precinct',
            height=400,
            hover_data={'hover_text': True, 'display_name': False, 'voters': False, 'Current Turf': False}
        )
        
        # Update hover template
        fig.update_traces(
            hovertemplate='%{customdata[0]}',
            customdata=hist_df[['hover_text']].values
        )
        
        # Update layout for better readability
        fig.update_layout(
            xaxis_tickangle=-45,
            showlegend=True,
            xaxis_title="Precinct",
            yaxis_title="Number of Voters",
            hoverlabel=dict(bgcolor="white", font_size=13)
        )
        
        st.plotly_chart(fig, use_container_width=True)

# Data Editor Section
if len(filtered_metrics) > 0:
    st.subheader("Edit Precinct Assignments")
    
    # Prepare data for editing - sorted by Current Turf, then van_precinct_name
    edit_df = filtered_metrics.sort_values(['Current Turf', 'van_precinct_name'])[
        ['van_precinct_id', 'van_precinct_name', 'county_name', 
         'Current Region', 'Current Turf', 'voters', 'supporters']
    ].copy()
    
    # Add empty columns for updates
    edit_df['Updated Region'] = None
    edit_df['Updated Turf'] = None
    
    # Get all possible regions and turfs for dropdowns
    all_regions = sorted(st.session_state.master_df['Current Region'].unique())
    all_turfs = sorted(st.session_state.master_df['Current Turf'].unique())
    
    # Configure column settings for the editor
    column_config = {
        "van_precinct_id": st.column_config.TextColumn("van_precinct_id", disabled=True),
        "van_precinct_name": st.column_config.TextColumn("van_precinct_name", disabled=True),
        "county_name": st.column_config.TextColumn("County", disabled=True),
        "Current Region": st.column_config.TextColumn("Current Region", disabled=True),
        "Current Turf": st.column_config.TextColumn("Current Turf", disabled=True),
        "voters": st.column_config.NumberColumn("Voters", disabled=True, format="%,d"),
        "supporters": st.column_config.NumberColumn("Supporters", disabled=True, format="%,d"),
        "Updated Region": st.column_config.SelectboxColumn(
            "Updated Region",
            help="Select new region assignment",
            options=all_regions,
            required=False
        ),
        "Updated Turf": st.column_config.SelectboxColumn(
            "Updated Turf",
            help="Select new turf assignment",
            options=all_turfs,
            required=False
        )
    }
    
    # Display the data editor
    edited_df = st.data_editor(
        edit_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        key="precinct_editor"
    )
    
    # Apply Changes button
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("Apply Changes", type="primary"):
            # Find rows with updates
            updates_made = False
            for idx, row in edited_df.iterrows():
                if pd.notna(row['Updated Region']) or pd.notna(row['Updated Turf']):
                    precinct_id = row['van_precinct_id']
                    
                    # Update the master dataframe
                    mask = st.session_state.master_df['van_precinct_id'] == precinct_id
                    
                    if pd.notna(row['Updated Region']):
                        st.session_state.master_df.loc[mask, 'Current Region'] = row['Updated Region']
                        updates_made = True
                    
                    if pd.notna(row['Updated Turf']):
                        st.session_state.master_df.loc[mask, 'Current Turf'] = row['Updated Turf']
                        updates_made = True
                    
                    # Track this precinct as changed
                    st.session_state.changed_precincts.add(precinct_id)
            
            if updates_made:
                st.success("Changes applied! Map will update automatically.")
                st.rerun()
            else:
                st.warning("No changes to apply. Select new regions or turfs first.")
    
    with col2:
        if st.button("Reset All Changes", type="secondary"):
            if st.session_state.changed_precincts:
                st.session_state.master_df = load_metrics()
                st.session_state.changed_precincts = set()
                st.success("All changes reset!")
                st.rerun()
            else:
                st.info("No changes to reset.")
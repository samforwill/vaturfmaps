import pandas as pd

df = pd.read_csv('data/master_precinct_shapes.csv')
unity_reed = df[df['van_precinct_name'] == '106 - Unity Reed']

unity_reed.to_csv('output/unity_reed.csv', index=False)
# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.
import pandas as pd
from dash import Dash, dcc, html, dash_table
from dash.dependencies import Output, Input, State
from dash_extensions.enrich import Output, DashProxy, Input, MultiplexerTransform
import dash_bootstrap_components as dbc
import plotly.express as px
import json
import numpy as np
from pathlib import Path
import statistics as stat
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import sqlite3
from run_query import get_pressure, get_discharge
from layout import layout
from changes import apply_changes

# Declare the database file name here
db_name = "copy.db"

# app = Dash(external_stylesheets=[dbc.themes.FLATLY])
app = DashProxy(external_stylesheets=[dbc.themes.FLATLY],
                prevent_initial_callbacks=True, transforms=[MultiplexerTransform()])

app.layout = layout


@app.callback(
    Output('mean', 'children'),
    Output('variance', 'children'),
    Input('indicator-graphic', 'selectedData'))
def display_selected(selection):
    print(selection)

    if selection is not None:
        pressures_selected = []
        for point in selection['points']:
            pressures_selected.append(point['y'])

        pressures_selected = pd.DataFrame(pressures_selected)

        return pressures_selected.mean(), pressures_selected.var()

    else:
        return 0, 0


@app.callback(
    Output('memory-output', 'data'),
    Input('query', 'n_clicks'),
    State('site_id', 'value'))
def main_query(n_clicks, site_id):
    # Opening the database file
    print(f"button clicked {n_clicks} times")
    if db_name.endswith(".db"):
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()  # This object will allow queries to be ran on the database
    else:
        print("Cannot open database file")

    # SQL query on the database -- Depending on your database, this will need to be formatted
    # to fit your system requirements
    pressure_data = get_pressure(cursor, site_id)
    # discharge_data = get_discharge(cursor, site_id)
    table = pd.DataFrame(pressure_data)
    table['pressure_hobo'].replace('', np.nan, inplace=True)
    table.dropna(subset=['pressure_hobo'], inplace=True)
    table.drop('index', axis=1, inplace=True)

    data = table.to_json()
    return data


# @app.callback(
#     Output('selected', 'children'),
#     Input('indicator-graphic', 'clickData'))
# def display_selected(clickData):
#     return json.dumps(clickData, indent=1)


@app.callback(
    Output('update-table', 'children'),
    Input('indicator-graphic', 'selectedData'),
    State('memory-output', 'data'),
    State('updated-table', 'data')
)
def display_selected_data(selectedData, data, updatedData):
    pressure_table = pd.read_json(data)
    if selectedData is not None:
        selected_styles = update_table_style(selectedData)
        if updatedData is not None:
            pressure_table = pd.read_json(updatedData)
            return html.Div(
                [
                    dash_table.DataTable(
                        data=pressure_table.to_dict('rows'),
                        columns=[{'id': x, 'name': x} for x in pressure_table.columns],
                        style_data_conditional=selected_styles,
                    )
                ]
            )
        else:
            return html.Div(
                [
                    dash_table.DataTable(
                        data=pressure_table.to_dict('rows'),
                        columns=[{'id': x, 'name': x} for x in pressure_table.columns],
                        style_data_conditional=selected_styles,
                    )
                ]
            )
    else:
        pass


def update_table_style(selectedData):
    points_selected = []
    for point in selectedData['points']:
        points_selected.append(point['pointIndex'])
    selected_styles = [{'if': {'row_index': i},
                        'backgroundColor': 'pink'} for i in points_selected]

    return selected_styles


def dataframe_from_selection(data, selection):
    df = pd.read_json(data)

    if selection is not None:
        datetimes_selected = []
        pressures_selected = []
        # Add points from the selection
        for point in selection['points']:
            datetimes_selected.append(point['x'])
            pressures_selected.append(point['y'])
        # Search data for datetime matches
        datetimes_series = df['datetime'].isin(datetimes_selected)
        matched_datetimes = df[datetimes_series]
        # Search datetime matches for y-value matches
        pressures_series = matched_datetimes['pressure_hobo'].isin(pressures_selected);
        matched_points = matched_datetimes[pressures_series]

        return matched_points

@app.callback(
    Output('memory-output', 'data'),
    Input('shift_button', 'n_clicks'),
    State('memory-output', 'data'),
    State('history', 'data'),
    State('shift_amount', 'value'),
    State('indicator-graphic', 'selectedData'))
def shift_selected_data(n_clicks, data, history, shift, selectedData):
    if n_clicks > 0 and shift is not None and selectedData is not None:
        data_df = pd.read_json(data)
        change_df = dataframe_from_selection(data, selectedData)

        if shift is not None:
            change_df['pressure_hobo'] = shift
            changed_df = apply_changes(data_df, change_df)

            return changed_df.to_json()
    else:
        pass


@app.callback(
    Output('memory-output', 'data'),
    Input('compress_button', 'n_clicks'),
    State('memory-output', 'data'),
    State('history', 'data'),
    State('compression_factor', 'value'),
    State('indicator-graphic', 'selectedData'))
def compress_selected_data(n_clicks, data, history, expcomp, selectedData):
    data_df = pd.read_json(data)
    if n_clicks > 0 and expcomp is not None and selectedData is not None:
        change_df = dataframe_from_selection(data, selectedData)

        if expcomp is not None:
            change_df_mean = stat.mean(change_df['pressure_hobo'])
            change_df['pressure_hobo'] = -(change_df['pressure_hobo'] - change_df_mean) / expcomp

            changed_df = apply_changes(data_df, change_df)

            return changed_df.to_json()
    else:
        pass


@app.callback(
    Output('memory-output', 'data'),
    Input('delete', 'n_clicks'),
    State('indicator-graphic', 'selectedData'),
    State('memory-output', 'data'))
def delete_button(n_clicks, selection, data):
    # Read in dataframe from local JSON store.
    df = pd.read_json(data)

    if selection is not None:
        change_df = dataframe_from_selection(data, selection)

        # remove the data points from the data frame
        df.drop(change_df.index, axis=0, inplace=True)

        # Save the data into the Local json store and trigger the graph update.
        return df.to_json()
    else:
        pass


@app.callback(
    Input('memory-output', 'data'),
    Output('indicator-graphic', 'figure'),
    Output('update-table', 'children'))
def update_on_new_data(data):
    # Read in dataframe from JSON
    df = pd.read_json(data)

    # Convert batch_id to strings
    df['batch_id'] = df['batch_id'].apply(lambda x: str(x))

    # Create a scatterplot figure from the dataframe
    figure = px.scatter(df, x=df.datetime, y=df.pressure_hobo,
                        color=df.batch_id)

    # create a DashTable from the data
    table = html.Div(
        [
            dash_table.DataTable(
                data=df.to_dict('rows'),
                columns=[{'id': x, 'name': x} for x in df.columns],
            )
        ]
    )

    # return objects into the graph and table
    return figure, table


@app.callback(
    Output('download-csv', 'data'),
    Input('exportDF', 'n_clicks'),
    State('memory-output', 'data'),
    State('export_filename', 'value'),
    prevent_initial_call=True
)
def export(n_clicks, data, filename):
    if data is not None:
        pressure_table = pd.read_json(data)
        return dcc.send_data_frame(pressure_table.to_csv, filename)


if __name__ == '__main__':
    app.run_server(debug=True)

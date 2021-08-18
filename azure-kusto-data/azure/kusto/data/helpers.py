from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import pandas
    from azure.kusto.data._models import KustoResultTable, KustoStreamingResultTable


# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License
def to_pandas_timedelta(raw_value) -> "pandas.Timedelta":
    """
    Transform a raw python value to a pandas timedelta.
    """
    import pandas as pd

    if isinstance(raw_value, (int, float)):
        # https://docs.microsoft.com/en-us/dotnet/api/system.datetime.ticks
        # Kusto saves up to ticks, 1 tick == 100 nanoseconds
        return pd.to_timedelta(raw_value * 100, unit="ns")
    if isinstance(raw_value, str):
        # The timespan format Kusto returns is 'd.hh:mm:ss.ssssss' or 'hh:mm:ss.ssssss' or 'hh:mm:ss'
        # Pandas expects 'd days hh:mm:ss.ssssss' or 'hh:mm:ss.ssssss' or 'hh:mm:ss'
        parts = raw_value.split(":")
        if "." not in parts[0]:
            return pd.to_timedelta(raw_value)
        else:
            formatted_value = raw_value.replace(".", " days ", 1)
            return pd.to_timedelta(formatted_value)


def dataframe_from_result_table(table: "Union[KustoResultTable, KustoStreamingResultTable]"):
    """Converts Kusto tables into pandas DataFrame.
    :param azure.kusto.data._models.KustoResultTable table: Table received from the response.
    :return: pandas DataFrame.
    """
    import pandas as pd

    if not table:
        raise ValueError()

    from azure.kusto.data._models import KustoResultTable, KustoStreamingResultTable

    if not isinstance(table, KustoResultTable) and not isinstance(table, KustoStreamingResultTable):
        raise TypeError("Expected KustoResultTable or KustoStreamingResultTable got {}".format(type(table).__name__))

    columns = [col.column_name for col in table.columns]
    frame = pd.DataFrame(table.raw_rows, columns=columns)

    # fix types
    for col in table.columns:
        if col.column_type == "bool":
            frame[col.column_name] = frame[col.column_name].astype(bool)
        if col.column_type == "datetime":
            frame[col.column_name] = pd.to_datetime(frame[col.column_name])
        if col.column_type == "timespan":
            frame[col.column_name] = frame[col.column_name].apply(to_pandas_timedelta)

    return frame

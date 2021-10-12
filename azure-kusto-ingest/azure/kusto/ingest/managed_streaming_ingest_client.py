from io import SEEK_SET
from typing import TYPE_CHECKING, Union, Optional, IO, AnyStr

from azure.kusto.data import KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoApiError
from . import IngestionProperties, BlobDescriptor, StreamDescriptor, FileDescriptor
from .base_ingest_client import BaseIngestClient
from .helpers import get_stream_size, sleep_with_backoff
from .ingest_client import QueuedIngestClient
from .streaming_ingest_client import KustoStreamingIngestClient

if TYPE_CHECKING:
    import pandas


class ManagedStreamingIngestClient(BaseIngestClient):
    RETRY_COUNT = 3
    MAX_STREAMING_SIZE = 4 * 1024 * 1024
    STREAMING_INGEST_EXCEPTION = "Kusto.DataNode.Exceptions.StreamingIngestionRequestException"

    def __init__(self, queued_kcsb: Union[KustoConnectionStringBuilder, str], streaming_kcsb: Optional[Union[KustoConnectionStringBuilder, str]] = None):
        if streaming_kcsb is None:
            streaming_kcsb = KustoConnectionStringBuilder(repr(queued_kcsb).replace("https://ingest-", "https://"))

        self.queued_client = QueuedIngestClient(queued_kcsb)
        self.streaming_client = KustoStreamingIngestClient(streaming_kcsb)

    def ingest_from_file(self, file_descriptor: Union[FileDescriptor, str], ingestion_properties: IngestionProperties):
        stream, stream_descriptor = self._prepare_stream_descriptor_from_file(file_descriptor)

        with stream:
            self.ingest_from_stream(stream_descriptor, ingestion_properties)

    def ingest_from_stream(self, stream_descriptor: Union[IO[AnyStr], StreamDescriptor], ingestion_properties: IngestionProperties):
        if not isinstance(stream_descriptor, StreamDescriptor):
            stream_descriptor = StreamDescriptor(stream_descriptor)
        stream = self._prepare_stream(stream_descriptor, ingestion_properties)

        if not stream.seekable():
            ...  # TODO - We need the stream to be seekable to do retries, so what's the correct thing to do here:
            # 1. Raise an exception saying we don't support non-seekable streams
            # 2. Read the stream into a list and wrap with BytesIO (might use lots of memory)
            # 3. Send it directly to queued ingest

        if get_stream_size(stream) > self.MAX_STREAMING_SIZE:
            return self.queued_client.ingest_from_stream(stream_descriptor, ingestion_properties)

        for i in range(self.RETRY_COUNT + 1):
            try:
                return self.streaming_client.ingest_from_stream(stream_descriptor, ingestion_properties)
            except KustoApiError as e:
                error = e.get_api_error()
                if error.permanent:
                    if error.type == self.STREAMING_INGEST_EXCEPTION:  # If the error is directly related to streaming ingestion, we might succeed in queued
                        break
                    raise
                stream.seek(0, SEEK_SET)
                if i != self.RETRY_COUNT:
                    sleep_with_backoff(i)

        return self.queued_client.ingest_from_stream(stream_descriptor, ingestion_properties)

    def ingest_from_dataframe(self, df: "pandas.DataFrame", ingestion_properties: IngestionProperties):
        return super().ingest_from_dataframe(df, ingestion_properties)

    def ingest_from_blob(self, blob_descriptor: BlobDescriptor, ingestion_properties: IngestionProperties):
        """
        Enqueue an ingest command from azure blobs.

        For ManagedStreamingIngestClient, this method always uses Queued Ingest, since it would be easier and faster to ingest blobs.

        To learn more about ingestion methods go to:
        https://docs.microsoft.com/en-us/azure/data-explorer/ingest-data-overview#ingestion-methods
        :param azure.kusto.ingest.BlobDescriptor blob_descriptor: An object that contains a description of the blob to be ingested.
        :param azure.kusto.ingest.IngestionProperties ingestion_properties: Ingestion properties.
        """
        return self.queued_client.ingest_from_blob(blob_descriptor, ingestion_properties)

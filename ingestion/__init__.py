"""WinScope Ingestion Package."""
from ingestion.pipeline import TelemetryIngestionPipeline
from ingestion.quality import DataQualityReport

__all__ = ["TelemetryIngestionPipeline", "DataQualityReport"]

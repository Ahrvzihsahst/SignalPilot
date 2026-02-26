"""Scan pipeline: composable stages for the main scanning loop."""

from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stage import PipelineStage, ScanPipeline

__all__ = ["PipelineStage", "ScanContext", "ScanPipeline"]

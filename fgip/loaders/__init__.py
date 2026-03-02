"""FGIP Loaders - External data ingestion modules.

Loaders import pre-processed data from external sources (ChatGPT analysis,
external databases, etc.) and merge with the FGIP knowledge graph.
"""

from .chatgpt_signal import (
    load_chatgpt_signal,
    ChatGPTSignalReport,
    ChannelClassification,
    SignalEntry,
    get_channel_classification,
    get_guest_weight,
    get_category_distribution,
    get_signal_entries_for_guest,
    get_signal_entries_for_channel,
    export_merged_report,
)

__all__ = [
    # Main loader
    "load_chatgpt_signal",
    # Data classes
    "ChatGPTSignalReport",
    "ChannelClassification",
    "SignalEntry",
    # Query functions
    "get_channel_classification",
    "get_guest_weight",
    "get_category_distribution",
    "get_signal_entries_for_guest",
    "get_signal_entries_for_channel",
    # Export
    "export_merged_report",
]

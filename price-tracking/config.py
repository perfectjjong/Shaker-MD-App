#!/usr/bin/env python3
"""
Price Tracking - Shared Configuration
Each channel uses this to locate its Master Excel file in the centralized data/ directory.
"""
import os
from pathlib import Path

# Root of price-tracking module
PT_ROOT = Path(__file__).parent.resolve()

# Centralized data directory (Excel Masters, Git LFS tracked)
DATA_DIR = PT_ROOT / "data"

# Channel name → Master Excel filename mapping
MASTER_FILES = {
    "extra":       "extra_master.xlsx",
    "bh":          "bh_master.xlsx",
    "sws":         "sws_master.xlsx",
    "najm":        "najm_master.xlsx",
    "alkhunaizan": "alkhunaizan_master.xlsx",
    "almanea":     "almanea_master.xlsx",
    "tamkeen":     "tamkeen_master.xlsx",
    "binmomen":    "binmomen_master.xlsx",
    "blackbox":    "blackbox_master.xlsx",
    "technobest":  "technobest_master.xlsx",
}

# BH Wholesale input directory
BH_WHOLESALE_DIR = DATA_DIR / "bh_wholesale_input"

# Dashboard output directory (docs/dashboards/ in repo root)
REPO_ROOT = PT_ROOT.parent
DASHBOARDS_DIR = REPO_ROOT / "docs" / "dashboards"

# Dashboard output paths per channel
DASHBOARD_PATHS = {
    "extra":       DASHBOARDS_DIR / "extra-price" / "index.html",
    "bh":          DASHBOARDS_DIR / "bh-price" / "index.html",
    "sws":         DASHBOARDS_DIR / "sws-price" / "index.html",
    "najm":        DASHBOARDS_DIR / "najm-price" / "index.html",
    "alkhunaizan": DASHBOARDS_DIR / "alkhunaizan-price" / "index.html",
    "almanea":     DASHBOARDS_DIR / "almanea-price" / "index.html",
    "tamkeen":     DASHBOARDS_DIR / "tamkeen-price" / "index.html",
    "binmomen":    DASHBOARDS_DIR / "binmomen-price" / "index.html",
    "blackbox":    DASHBOARDS_DIR / "blackbox-price" / "index.html",
    "technobest":  DASHBOARDS_DIR / "technobest-price" / "index.html",
}


def get_master_path(channel: str) -> Path:
    """Get the absolute path to a channel's Master Excel file."""
    return DATA_DIR / MASTER_FILES[channel]


def get_dashboard_path(channel: str) -> Path:
    """Get the absolute path to a channel's dashboard HTML output."""
    return DASHBOARD_PATHS[channel]


# Environment variable override (for local development)
if os.environ.get("PT_DATA_DIR"):
    DATA_DIR = Path(os.environ["PT_DATA_DIR"])

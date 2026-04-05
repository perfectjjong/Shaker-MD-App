#!/usr/bin/env python3
"""
Price Tracking Orchestrator
===========================
Runs all 10 channel scrapers sequentially, then copies dashboards to docs/.
Designed for both GitHub Actions and local execution.

Usage:
  python orchestrator.py              # Run all channels
  python orchestrator.py extra bh     # Run specific channels only
  python orchestrator.py --dashboard-only  # Skip scraping, only rebuild dashboards
"""

import os
import sys
import shutil
import subprocess
import time
import argparse
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────
PT_ROOT = Path(__file__).parent.resolve()
CHANNELS_DIR = PT_ROOT / "channels"
DATA_DIR = PT_ROOT / "data"
REPO_ROOT = PT_ROOT.parent
DASHBOARDS_DIR = REPO_ROOT / "docs" / "dashboards"

# Python executable
PYTHON = sys.executable

# ── Channel definitions ────────────────────────────────────────
# Each channel: (folder_name, master_data_filename, original_master_filename, steps)
CHANNELS = {
    "extra": {
        "dir": "extra",
        "master_data": "extra_master.xlsx",
        "master_local": "extra_ac_Prices_Tracking_Master.xlsx",
        "steps": [
            ("extra_ac_scraper_v4.py", "Scraping (Playwright)"),
            ("extra_ac_dashboard_builder.py", "Dashboard Builder (Excel)"),
            ("extra_ac_html_dashboard_v2.py", "HTML Dashboard"),
        ],
        "dashboard_html": "extra_ac_dashboard_v2.html",
        "dashboard_dest": "extra-price",
    },
    "bh": {
        "dir": "bh",
        "master_data": "bh_master.xlsx",
        "master_local": "BH_Subdealer_AC_Master.xlsx",
        "steps": [
            ("consolidate_ac.py", "Scraping + Excel Master"),
            ("bh_ac_html_dashboard_v2.py", "HTML Dashboard"),
        ],
        "dashboard_html": "bh_ac_dashboard_v2.html",
        "dashboard_dest": "bh-price",
    },
    "sws": {
        "dir": "sws",
        "master_data": "sws_master.xlsx",
        "master_local": "SWS_AC_Price_Tracking_Master.xlsx",
        "steps": [
            ("swsg_ac_scraper_v12.py", "Scraping (Playwright)"),
            ("sws_ac_html_dashboard.py", "HTML Dashboard"),
        ],
        "dashboard_html": "sws_ac_dashboard.html",
        "dashboard_dest": "sws-price",
    },
    "najm": {
        "dir": "najm",
        "master_data": "najm_master.xlsx",
        "master_local": "najm_ac_master.xlsx",
        "steps": [
            ("najm_scraper.py", "Scraping (API)"),
            ("najm_ac_html_dashboard.py", "HTML Dashboard"),
        ],
        "dashboard_html": "najm_ac_dashboard.html",
        "dashboard_dest": "najm-price",
    },
    "alkhunaizan": {
        "dir": "alkhunaizan",
        "master_data": "alkhunaizan_master.xlsx",
        "master_local": "AlKhunaizan_AC_Prices Tracking_Master.xlsx",
        "steps": [
            ("AC_Scraper_AlKhunaizan_v8_2.py", "Scraping (Playwright)"),
            ("alkhunaizan_dashboard_builder.py", "Dashboard Builder (Excel)"),
            ("alkhunaizan_ac_html_dashboard_v2.py", "HTML Dashboard"),
        ],
        "dashboard_html": "alkhunaizan_ac_dashboard_v2.html",
        "dashboard_dest": "alkhunaizan-price",
    },
    "almanea": {
        "dir": "almanea",
        "master_data": "almanea_master.xlsx",
        "master_local": "Almanea_AC_Price_Tracking_Master.xlsx",
        "steps": [
            ("almanea_ac_v3.py", "Scraping (API)"),
            ("almanea_ac_master_dashboard.py", "Dashboard Builder (Excel)"),
            ("almanea_ac_html_dashboard_v2.py", "HTML Dashboard"),
        ],
        "dashboard_html": "almanea_ac_dashboard_v2.html",
        "dashboard_dest": "almanea-price",
    },
    "tamkeen": {
        "dir": "tamkeen",
        "master_data": "tamkeen_master.xlsx",
        "master_local": "tamkeen_master.xlsx",  # Tamkeen uses snapshot pattern
        "steps": [
            ("tamkeen_final_scraper.py", "Scraping (Playwright/Firefox)"),
            ("tamkeen_ac_html_dashboard.py", "HTML Dashboard"),
        ],
        "dashboard_html": "tamkeen_ac_dashboard.html",
        "dashboard_dest": "tamkeen-price",
    },
    "binmomen": {
        "dir": "binmomen",
        "master_data": "binmomen_master.xlsx",
        "master_local": "Binmomen_AC_Prices_Tracking_Master.xlsx",
        "steps": [
            ("binmomen_ac_scraper.py", "Scraping (Requests)"),
            ("binmomen_ac_dashboard_builder.py", "Dashboard Builder (Excel)"),
            ("binmomen_ac_html_dashboard.py", "HTML Dashboard"),
        ],
        "dashboard_html": "binmomen_ac_dashboard.html",
        "dashboard_dest": "binmomen-price",
    },
    "blackbox": {
        "dir": "blackbox",
        "master_data": "blackbox_master.xlsx",
        "master_local": "Black Box_AC_Price tracking_Master.xlsx",
        "steps": [
            ("blackbox_ac_scraper.py", "Scraping (Playwright + API)"),
            ("blackbox_ac_dashboard_builder.py", "Dashboard Builder (Excel)"),
            ("blackbox_ac_html_dashboard_v2.py", "HTML Dashboard"),
        ],
        "dashboard_html": "blackbox_ac_dashboard_v2.html",
        "dashboard_dest": "blackbox-price",
    },
    "technobest": {
        "dir": "technobest",
        "master_data": "technobest_master.xlsx",
        "master_local": "TechnoBest_AC_Master.xlsx",
        "steps": [
            ("technobest_ac_scraper.py", "Scraping (API)"),
            ("technobest_ac_html_dashboard.py", "HTML Dashboard"),
        ],
        "dashboard_html": "technobest_ac_dashboard.html",
        "dashboard_dest": "technobest-price",
    },
}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def copy_master_to_channel(channel_name: str, config: dict):
    """Copy Master Excel from data/ to channel directory (so scrapers find it)."""
    src = DATA_DIR / config["master_data"]
    dst = CHANNELS_DIR / config["dir"] / config["master_local"]
    if src.exists():
        shutil.copy2(src, dst)
        log(f"  {channel_name}: data/{config['master_data']} -> channels/{config['dir']}/{config['master_local']}")
    else:
        log(f"  {channel_name}: WARNING - {src} not found (first run?)")


def copy_master_from_channel(channel_name: str, config: dict):
    """Copy updated Master Excel from channel directory back to data/."""
    src = CHANNELS_DIR / config["dir"] / config["master_local"]
    dst = DATA_DIR / config["master_data"]

    # Special handling for Tamkeen: find latest Tamkeen_Complete_*.xlsx
    if channel_name == "tamkeen":
        channel_dir = CHANNELS_DIR / config["dir"]
        tamkeen_files = sorted(channel_dir.glob("Tamkeen_Complete_*.xlsx"), reverse=True)
        tamkeen_files = [f for f in tamkeen_files if "partial" not in f.name]
        if tamkeen_files:
            src = tamkeen_files[0]
            log(f"  {channel_name}: Latest snapshot -> {src.name}")

    if src.exists():
        shutil.copy2(src, dst)
        log(f"  {channel_name}: Updated master -> data/{config['master_data']}")
    else:
        log(f"  {channel_name}: WARNING - No master file found at {src}")


def copy_dashboard(channel_name: str, config: dict):
    """Copy generated HTML dashboard to docs/dashboards/."""
    src = CHANNELS_DIR / config["dir"] / config["dashboard_html"]
    dest_dir = DASHBOARDS_DIR / config["dashboard_dest"]
    dest_file = dest_dir / "index.html"

    if src.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_file)
        log(f"  {channel_name}: {config['dashboard_html']} -> docs/dashboards/{config['dashboard_dest']}/index.html")
    else:
        log(f"  {channel_name}: WARNING - Dashboard HTML not found: {src}")


def run_channel(channel_name: str, config: dict, dashboard_only: bool = False) -> dict:
    """Run all steps for a single channel."""
    channel_dir = CHANNELS_DIR / config["dir"]
    results = {"channel": channel_name, "steps": [], "success": True}

    log(f"\n{'='*60}")
    log(f"  Channel: {channel_name.upper()}")
    log(f"{'='*60}")

    # Step 0: Copy master from data/ to channel directory
    copy_master_to_channel(channel_name, config)

    steps = config["steps"]
    if dashboard_only:
        # Only run the last step (HTML dashboard)
        steps = [s for s in steps if "html" in s[0].lower() or "dashboard" in s[1].lower()]
        if not steps:
            steps = [config["steps"][-1]]

    for i, (script, description) in enumerate(steps, 1):
        script_path = channel_dir / script
        log(f"  [{i}/{len(steps)}] {description} ({script})")

        if not script_path.exists():
            log(f"    SKIP - File not found: {script_path}")
            results["steps"].append({"script": script, "status": "skip"})
            continue

        start = time.time()
        try:
            result = subprocess.run(
                [PYTHON, "-X", "utf8", "-u", str(script_path)],
                cwd=str(channel_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=1800,  # 30 min per step
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            elapsed = time.time() - start

            if result.returncode == 0:
                log(f"    OK ({elapsed:.0f}s)")
                results["steps"].append({"script": script, "status": "ok", "elapsed": elapsed})
            else:
                log(f"    FAILED (exit={result.returncode}, {elapsed:.0f}s)")
                if result.stderr:
                    # Show last 5 lines of stderr
                    for line in result.stderr.strip().split('\n')[-5:]:
                        log(f"      {line}")
                results["steps"].append({"script": script, "status": "fail", "elapsed": elapsed})
                results["success"] = False
                break  # Stop this channel on failure

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            log(f"    TIMEOUT ({elapsed:.0f}s)")
            results["steps"].append({"script": script, "status": "timeout", "elapsed": elapsed})
            results["success"] = False
            break
        except Exception as e:
            log(f"    ERROR: {e}")
            results["steps"].append({"script": script, "status": "error", "error": str(e)})
            results["success"] = False
            break

    # Step N+1: Copy updated master back to data/
    if not dashboard_only:
        copy_master_from_channel(channel_name, config)

    # Step N+2: Copy dashboard HTML to docs/
    copy_dashboard(channel_name, config)

    return results


def main():
    parser = argparse.ArgumentParser(description="Price Tracking Orchestrator")
    parser.add_argument("channels", nargs="*", help="Specific channels to run (default: all)")
    parser.add_argument("--dashboard-only", action="store_true", help="Skip scraping, only rebuild dashboards")
    args = parser.parse_args()

    # UTF-8 console
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Select channels
    if args.channels:
        selected = {k: v for k, v in CHANNELS.items() if k in args.channels}
        if not selected:
            print(f"Unknown channels: {args.channels}")
            print(f"Available: {', '.join(CHANNELS.keys())}")
            sys.exit(1)
    else:
        selected = CHANNELS

    # Banner
    run_start = datetime.now()
    log("=" * 60)
    log("  Price Tracking Orchestrator")
    log(f"  Date: {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  Channels: {', '.join(selected.keys())} ({len(selected)})")
    log(f"  Mode: {'Dashboard only' if args.dashboard_only else 'Full (scrape + dashboard)'}")
    log("=" * 60)

    # Run each channel
    all_results = []
    for channel_name, config in selected.items():
        result = run_channel(channel_name, config, args.dashboard_only)
        all_results.append(result)

    # Summary
    run_end = datetime.now()
    elapsed = (run_end - run_start).total_seconds()
    succeeded = sum(1 for r in all_results if r["success"])
    failed = len(all_results) - succeeded

    log(f"\n{'='*60}")
    log(f"  SUMMARY")
    log(f"  Total: {len(all_results)} channels")
    log(f"  OK: {succeeded} | FAILED: {failed}")
    log(f"  Duration: {int(elapsed//60)}m {int(elapsed%60)}s")
    log(f"{'='*60}")

    for r in all_results:
        status = "OK" if r["success"] else "FAIL"
        steps_info = ", ".join(f"{s['script']}:{s['status']}" for s in r["steps"])
        log(f"  [{status}] {r['channel']}: {steps_info}")

    # Exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

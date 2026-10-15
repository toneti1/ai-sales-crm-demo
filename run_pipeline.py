"""End-to-end orchestration for the AI Sales Assistant.

Runs lead-finder, integrates output with the generator, and prepares the
unified lead database for the dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
LEAD_FINDER_DIR = ROOT_DIR / "lead-finder"
GENERATOR_DIR = ROOT_DIR / "generator"
UNIFIED_LEADS_FILE = ROOT_DIR / "unified_leads.json"


def _node_executable() -> str:
    """Locate the node runtime: portable bundle shipped with the demo, else PATH."""
    portable = ROOT_DIR / "node" / ("node.exe" if sys.platform == "win32" else "node")
    if portable.exists():
        return str(portable)
    system_node = shutil.which("node")
    if system_node:
        return system_node
    raise RuntimeError("node is required to run lead-finder (not found in PATH).")


def _ensure_chromium_env() -> None:
    """Point Puppeteer at the bundled Chrome when present."""
    if "PUPPETEER_EXECUTABLE_PATH" in os.environ:
        return
    portable = ROOT_DIR / "chrome" / "chrome.exe"
    if portable.exists():
        os.environ["PUPPETEER_EXECUTABLE_PATH"] = str(portable)


def _run(cmd: list[str], cwd: Path, description: str) -> None:
    """Run a subprocess command and stream output."""
    print(f"\n>>> {description}")
    print(" ".join(cmd))
    result = subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True,
        encoding="utf-8", errors="replace",
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{description} failed with exit code {result.returncode}")


def _npm_available() -> bool:
    return shutil.which("npm") is not None


def _npm_cmd() -> str:
    """Return the npm executable name for the current platform."""
    return "npm.cmd" if sys.platform == "win32" else "npm"


def build_lead_finder() -> None:
    """Compile the TypeScript lead-finder CLI."""
    if not _npm_available():
        raise RuntimeError("npm is required to build lead-finder.")
    npm = _npm_cmd()
    _run([npm, "install"], LEAD_FINDER_DIR, "Installing lead-finder dependencies")
    _run([npm, "run", "build"], LEAD_FINDER_DIR, "Building lead-finder")


def run_lead_finder(city: str, sector: str, max_results: int | None) -> None:
    """Run the lead-finder CLI for a given city and sector."""
    _ensure_chromium_env()
    cmd = [
        _node_executable(),
        str(LEAD_FINDER_DIR / "dist" / "cli.js"),
        "--city",
        city,
        "--sector",
        sector,
    ]
    if max_results is not None:
        cmd.extend(["--max", str(max_results)])
    _run(cmd, LEAD_FINDER_DIR, f"Scraping leads for '{sector}' in '{city}'")


def run_integration() -> dict:
    """Run integrate.py and return the result summary."""
    _run([sys.executable, str(ROOT_DIR / "integrate.py")], ROOT_DIR, "Integrating leads with generator")
    return json.loads(UNIFIED_LEADS_FILE.read_text(encoding="utf-8"))


def run_follow_ups(delay_days: int) -> dict:
    """Run the follow-up email generator."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(GENERATOR_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sales_assistant_generator.followup",
            "--delay",
            str(delay_days),
        ],
        cwd=GENERATOR_DIR,
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError("Follow-up generation failed")
    return json.loads(UNIFIED_LEADS_FILE.read_text(encoding="utf-8"))


def start_dashboard(port: int) -> None:
    """Start the dashboard server."""
    os.environ["DASHBOARD_PORT"] = str(port)
    _run(
        [sys.executable, str(ROOT_DIR / "dashboard" / "server.py"), str(port)],
        ROOT_DIR,
        f"Starting dashboard on port {port}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full AI Sales Assistant pipeline.")
    parser.add_argument("--city", required=True, help="City to search for leads.")
    parser.add_argument("--sector", required=True, help="Business sector to search for.")
    parser.add_argument("--max", type=int, default=None, help="Maximum leads to scrape.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the lead-finder build step.")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping; use existing lead-finder/leads.json.")
    parser.add_argument("--follow-up-delay", type=int, default=7, help="Days before a follow-up email is due.")
    parser.add_argument("--dashboard", action="store_true", help="Start the dashboard server after pipeline steps.")
    parser.add_argument("--dashboard-port", type=int, default=8000, help="Port for the dashboard server.")
    args = parser.parse_args()

    try:
        if not args.skip_build:
            build_lead_finder()
        if not args.skip_scrape:
            run_lead_finder(args.city, args.sector, args.max)
        summary = run_integration()
        run_follow_ups(args.follow_up_delay)

        print("\n=== Pipeline complete ===")
        print(f"New leads added: {summary.get('newLeadsAdded', 0)}")
        print(f"Total leads in database: {summary.get('totalLeads', 0)}")
        print(f"Database: {UNIFIED_LEADS_FILE}")

        if args.dashboard:
            start_dashboard(args.dashboard_port)
        else:
            print("\nStart the dashboard with:")
            print("  python dashboard/server.py")
        return 0
    except Exception as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

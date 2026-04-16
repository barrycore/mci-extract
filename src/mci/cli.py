"""
mci.cli

Batch command-line interface for the MasterCard IPM parser.
Uses config.json (runtime) + mideu.yml (parsing + output fields).
"""

from __future__ import annotations

import logging
import json
import sys
from pathlib import Path

import typer
import yaml

from mci.parser import unblock, vbs_unpack, parse_record
from mci.export import to_csv, to_json

app = typer.Typer(
    name="mci-extract",
    help="Batch extract MasterCard IPM files using config.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resource_path(relative: str) -> Path:
    """Resolve path for dev + PyInstaller"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(relative)


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def resolve_mideu_config(filename: str) -> Path:
    """
    Resolve mideu.yml in ALL environments:
    1. Explicit path
    2. EXE bundled (_MEIPASS)
    3. Current working directory
    4. Home directory
    """

    # 1. Direct path
    p = Path(filename)
    if p.is_file():
        return p.resolve()

    # 2. PyInstaller bundled path
    bundled_path = resource_path(f"mci/{filename}")
    if bundled_path.is_file():
        return bundled_path.resolve()

    # 3. Current working directory
    cwd_path = Path.cwd() / filename
    if cwd_path.is_file():
        return cwd_path.resolve()

    # 4. Home directory
    home_path = Path.home() / filename
    if home_path.is_file():
        return home_path.resolve()

    raise FileNotFoundError(f"{filename} not found in any expected location.")

def resolve_config_path(config: str | None) -> Path:
    """
    Resolve config.json in this order:
    1. CLI argument (--config)
    2. Same folder as EXE
    3. Current working directory
    """
    if config:
        p = Path(config)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"Config not found: {config}")

    # PyInstaller EXE directory
    exe_dir = Path(sys.executable).parent

    candidates = [
        exe_dir / "config.json",
        Path.cwd() / "config.json",
    ]

    for p in candidates:
        if p.is_file():
            return p.resolve()

    raise FileNotFoundError(
        "config.json not found. Provide via --config or place it next to the executable."
    )
# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.command()
def run(
    config: str | None = typer.Option(
    None,
    "--config",
    "-c",
    help="Path to config.json (optional)"
),
):
    """
    Run batch extraction using config.json
    """

    # -----------------------------------------------------------------------
    # Load runtime config
    # -----------------------------------------------------------------------
    config_path = resolve_config_path(config)

    DEFAULT_CONFIG = {
    "input_dir": "input",
    "output_dir": "output",
    "format": "csv",
    "source_format": "ascii",
    "no_blocking": False,
    "verbose": True,
    "debug": False,
    "config_file": "mideu.yml"
}

    # Create config if missing
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        typer.echo(f"Created default config at {config_path}")


    app_cfg = load_json(config_path)

    input_dir = Path(app_cfg["input_dir"]).resolve()
    output_dir = Path(app_cfg["output_dir"]).resolve()

    fmt = app_cfg.get("format", "csv")
    source_format = app_cfg.get("source_format", "ascii")
    no_blocking = app_cfg.get("no_blocking", False)
    verbose = app_cfg.get("verbose", False)
    debug = app_cfg.get("debug", False)

    mideu_path = resolve_mideu_config(
    app_cfg.get("config_file", "mideu.yml")
)

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    log_level = logging.DEBUG if debug else (
        logging.INFO if verbose else logging.WARNING
    )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # -----------------------------------------------------------------------
    # Validate inputs
    # -----------------------------------------------------------------------
    if fmt not in ("csv", "json", "both"):
        typer.echo("[ERROR] format must be csv | json | both", err=True)
        raise typer.Exit(1)

    if not input_dir.exists():
        typer.echo(f"[ERROR] Input directory not found: {input_dir}", err=True)
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    if not mideu_path.is_file():
        typer.echo(f"[ERROR] mideu.yml not found: {mideu_path}", err=True)
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # Load parsing config (mideu.yml)
    # -----------------------------------------------------------------------
    mideu_cfg = load_yaml(mideu_path)

    bit_config = {
        int(k): v for k, v in mideu_cfg.get("bit_config", {}).items()
    }

    # 👇 default from YAML, optional override from config.json
    output_fields = app_cfg.get(
        "output_data_elements",
        mideu_cfg.get("output_data_elements", [])
    )

    # -----------------------------------------------------------------------
    # Find input files
    # -----------------------------------------------------------------------
    files = list(input_dir.glob("*.001"))

    if not files:
        typer.echo("No .001 files found in input directory.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(files)} file(s).")

    # -----------------------------------------------------------------------
    # Process files
    # -----------------------------------------------------------------------
    for file in files:
        typer.echo(f"\nProcessing {file.name} ...")

        raw = file.read_bytes()

        # unpack records
        records_raw = vbs_unpack(raw) if no_blocking else unblock(raw)

        parsed = []
        skipped = 0

        for i, rec in enumerate(records_raw):
            try:
                result = parse_record(rec, bit_config, source_format)
                if result:
                    parsed.append(result)
                else:
                    skipped += 1
            except Exception as exc:
                logging.debug("Record %d failed: %s", i, exc)
                skipped += 1

        typer.echo(f"Parsed {len(parsed)} records ({skipped} skipped).")

        if not parsed:
            typer.echo("Skipping file (no valid records).")
            continue

        out_base = output_dir / file.stem

        # -------------------------------------------------------------------
        # Write output
        # -------------------------------------------------------------------
        if fmt in ("csv", "both"):
            to_csv(str(out_base) + ".csv", parsed, output_fields)

        if fmt in ("json", "both"):
            to_json(str(out_base) + ".json", parsed)

        typer.echo(f"Done : {out_base}")

    typer.echo("\nAll files processed successfully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app()


if __name__ == "__main__":
    main()
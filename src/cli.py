from __future__ import annotations

import logging

import click

from .config import load_config

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="1.0.0", prog_name="solar-tool")
@click.option(
    "--config",
    "-c",
    default="config.yaml",
    show_default=True,
    help="Path to YAML configuration file.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable debug-level logging.",
)
@click.pass_context
def cli(ctx, config, verbose):
    """Solar rooftop potential calculator for DHN planning support.

    Computes solar thermal and PV potential from ERA5 weather data
    and open geodata (built-up rasters or LoD2 building models).
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(config)
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg


@cli.command()
@click.pass_context
def run(ctx):
    """Run a single-region solar potential analysis."""
    cfg = ctx.obj["config"]
    click.echo(f"Running analysis for region: {cfg.region.name}")
    click.echo(f"  Year: {cfg.parameters.year}")
    click.echo(f"  Capacity density: {cfg.parameters.capacity_density} MW/km²")

    approach = "lod2" if cfg.data.lod2_tiles else "raster"
    click.echo(f"  Approach: {approach}")
    click.echo()
    click.echo("Analysis pipeline not yet wired up -- coming soon.")


@cli.command()
@click.option(
    "--years",
    "-y",
    default="2000..2020",
    show_default=True,
    help="Year range (e.g. 2000..2020).",
)
@click.pass_context
def sweep(ctx, years):
    """Run a multi-year sweep for the configured region.

    Iterates over a range of years and collects results for
    inter-annual variability analysis.
    """
    try:
        parts = years.split("..")
        start, end = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise click.BadParameter(
            "years must be in the format START..END (e.g. 2000..2020)"
        )

    cfg = ctx.obj["config"]
    year_list = list(range(start, end + 1))
    click.echo(
        f"Sweeping {cfg.region.name} for {len(year_list)} years "
        f"({start}-{end})..."
    )
    click.echo()
    click.echo("Sweep pipeline not yet wired up -- coming soon.")


@cli.command()
@click.option("--year", "-y", default=2015, show_default=True,
              help="ERA5 year (cutout must already exist).")
def compare_orientation(year):
    """Compare actual roof orientation vs latitude-optimal.

    Requires an already-downloaded ERA5 cutout at data/era5-{year}-leeste.nc.
    """
    from analysis.orientation_comparison import run_comparison
    run_comparison(year=year)


def main():
    cli()

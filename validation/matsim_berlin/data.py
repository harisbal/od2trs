"""Download and load the open MATSim Berlin scenario: trips, persons and zones."""

from __future__ import annotations

import logging
import re
import urllib.request
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon

log = logging.getLogger(__name__)

SVN = "https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin"
# The scenario outputs are in UTM 32N; the zone shapefiles are in UTM 33N and ship
# without a .prj
MATSIM_CRS = "EPSG:25832"
ZONES_CRS = "EPSG:25833"
OUTPUT_FILES = ("output_trips.csv.gz", "output_persons.csv.gz")


def download(url: str, path: Path) -> Path:
    """Download `url` to `path` unless it is already there."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s", url)
    part = path.with_name(path.name + ".part")
    urllib.request.urlretrieve(url, part)
    part.rename(path)
    return path


def download_outputs(version: str, sample: str, data_dir: Path) -> dict[str, Path]:
    """Trips and persons of a published run; the run prefix (e.g. ``013.``) is read from
    the folder listing."""
    base = f"{SVN}/berlin-v{version}/output/berlin-v{version}-{sample}"
    with urllib.request.urlopen(base + "/") as r:
        listing = r.read().decode()
    paths = {}
    for name in OUTPUT_FILES:
        m = re.search(rf'href="([^"/]*{re.escape(name)})"', listing)
        if m is None:
            raise FileNotFoundError(f"No {name} in {base}")
        paths[name] = download(
            f"{base}/{m.group(1)}", data_dir / f"berlin-v{version}-{sample}" / name
        )
    return paths


def download_lor(version: str, layer: str, data_dir: Path) -> Path:
    """A Berlin LOR zone layer (Prognoseraum, Bezirksregion or Planungsraum)."""
    base = f"{SVN}/berlin-v{version}/input/shp"
    stem = f"{layer}_EPSG_25833"
    folder = data_dir / f"berlin-v{version}" / "shp"
    # The sidecar files are upper-case on the server
    for ext in ("shp", "SHX", "DBF"):
        download(f"{base}/{stem}.{ext}", folder / f"{stem}.{ext.lower()}")
    return folder / f"{stem}.shp"


def load_zones(version: str, layer: str, h3_resolution: int, data_dir: Path) -> gpd.GeoDataFrame:
    """Zones indexed by a text `Zone` id, with a `Name`, in the scenario CRS."""
    lor = "Prognoseraum" if layer == "h3" else layer
    zones = gpd.read_file(download_lor(version, lor, data_dir)).set_crs(ZONES_CRS)
    name_col = next(c for c in zones.columns if c.endswith("_NAME"))
    zones = zones.rename(columns={"SCHLUESSEL": "Zone", name_col: "Name"})
    zones = zones[["Zone", "Name", "geometry"]].to_crs(MATSIM_CRS)
    # Each layer has a couple of unnamed slivers (~0.1 km2)
    zones = zones.dropna(subset="Zone")
    if layer == "h3":
        zones = h3_grid(zones.union_all(), h3_resolution)
    return zones.set_index("Zone")


def h3_grid(area, resolution: int) -> gpd.GeoDataFrame:
    """H3 cells of `resolution` covering `area`, clipped to it."""
    # Fill a buffered area so the cells on the boundary are covered too
    edge = h3.average_hexagon_edge_length(resolution, unit="m")
    buffered = gpd.GeoSeries([area.buffer(2 * edge)], crs=MATSIM_CRS).to_crs("EPSG:4326")
    cells = sorted(h3.geo_to_cells(buffered.iloc[0], resolution))
    hexagons = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells]
    grid = gpd.GeoDataFrame({"Zone": cells}, geometry=hexagons, crs="EPSG:4326")
    grid = grid.to_crs(MATSIM_CRS)
    grid["geometry"] = grid.intersection(area)
    grid = grid[~grid.is_empty].copy()
    grid["Name"] = grid["Zone"]
    return grid[["Zone", "Name", "geometry"]]


def load_trips(path: Path) -> pd.DataFrame:
    """Trips with the departure in seconds and the activity types without their duration
    suffix (``home_86400`` -> ``home``)."""
    cols = [
        "person", "trip_number", "dep_time", "traveled_distance", "main_mode",
        "start_activity_type", "end_activity_type", "start_x", "start_y", "end_x", "end_y",
    ]  # fmt: skip
    trips = pd.read_csv(path, sep=";", usecols=cols)
    trips["dep_time"] = to_seconds(trips["dep_time"])
    for c in ("start_activity_type", "end_activity_type"):
        trips[c] = trips[c].str.replace(r"_\d+$", "", regex=True)
    return trips.sort_values(["person", "trip_number"], ignore_index=True)


def load_persons(path: Path) -> pd.DataFrame:
    cols = ["person", "subpopulation", "home_x", "home_y"]
    return pd.read_csv(path, sep=";", usecols=cols)


def to_seconds(hms: pd.Series) -> pd.Series:
    """``HH:MM:SS`` (hours may exceed 24) to seconds."""
    parts = hms.str.split(":", expand=True).astype(int)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]

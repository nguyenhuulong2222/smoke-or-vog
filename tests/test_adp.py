"""ADP -> candidate regions, with synthetic Kahu Ola-style Mercator masks."""

import math

from PIL import Image, ImageDraw

from src import geo, sources

MW, MH = 384, 293  # Kahu Ola ADP frame size (Web-Mercator canvas over the analysis box)


def merc_xy(lon, lat):
    def my(phi):
        return math.log(math.tan(math.pi / 4 + math.radians(phi) / 2))
    x = (lon - geo.WEST) / (geo.EAST - geo.WEST) * MW
    y = (my(geo.NORTH) - my(lat)) / (my(geo.NORTH) - my(geo.SOUTH)) * MH
    return x, y


def frame_with_blobs(blobs):
    """blobs: list of (lon0, lat0, lon1, lat1) rectangles drawn opaque on a transparent frame."""
    im = Image.new("RGBA", (MW, MH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for lon0, lat0, lon1, lat1 in blobs:
        x0, y0 = merc_xy(lon0, lat1)
        x1, y1 = merc_xy(lon1, lat0)
        d.rectangle([x0, y0, x1, y1], fill=(255, 200, 0, 200))
    return im


def box_lonlat(box):
    lon0, lat1 = geo.px_to_lonlat(box[0], box[1])
    lon1, lat0 = geo.px_to_lonlat(box[2] + 1, box[3] + 1)
    return lon0, lat0, lon1, lat1


def test_empty_frame_has_no_candidates():
    grid = sources.adp_mask_to_grid(Image.new("RGBA", (MW, MH), (0, 0, 0, 0)))
    assert grid.size == (geo.WIDTH, geo.HEIGHT)
    assert sources.adp_candidates(grid) == []


def test_single_plume_southwest_of_ka_lae_maps_to_right_place():
    # A vog-like blob SW of Ka Lae: lon -156.3..-155.7, lat 18.4..18.9
    target = (-156.3, 18.4, -155.7, 18.9)
    grid = sources.adp_mask_to_grid(frame_with_blobs([target]))
    cands = sources.adp_candidates(grid)
    assert len(cands) == 1
    got = box_lonlat(cands[0])
    tol = 0.04  # one Mercator canvas pixel is ~0.018 deg lon / ~0.017 deg lat
    for g, t in zip(got, target):
        assert abs(g - t) < tol, (got, target)


def test_mercator_reprojection_not_linear_in_latitude():
    # A blob near the north edge must land near the north edge of our grid, i.e. the
    # reprojection really uses Mercator (a linear mapping would shift it by several px).
    target = (-158.2, 22.5, -157.8, 22.9)
    cands = sources.adp_candidates(sources.adp_mask_to_grid(frame_with_blobs([target])))
    assert len(cands) == 1
    _, lat0, _, lat1 = box_lonlat(cands[0])
    assert abs(lat0 - 22.5) < 0.04 and abs(lat1 - 22.9) < 0.04


def test_two_separate_plumes_give_two_candidates_and_tiny_specks_dropped():
    blobs = [(-156.3, 18.4, -155.7, 18.9),     # Big Island vog
             (-157.0, 20.6, -156.6, 20.9),     # Maui smoke
             (-160.0, 22.0, -159.99, 22.01)]   # one-pixel speck
    cands = sources.adp_candidates(sources.adp_mask_to_grid(frame_with_blobs(blobs)))
    assert len(cands) == 2
    centers = sorted(((b[0] + b[2]) / 2 for b in cands))
    assert centers[0] < centers[1]

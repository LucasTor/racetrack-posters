"""Interlagos A3 poster: street-map background + STL files for track and wordmark.
Page coordinates are millimetres, origin top-left, A3 portrait (297 x 420)."""
import json, os, sys
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity
from svgpathtools import svg2paths2
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
W, H = 297.0, 420.0
SCALE = float(os.environ.get("SCALE", 5000))
TRACK_TOP = 42.0         # mm from top edge to the northernmost point of the track
TRACK_W = 3.0            # printed track width, mm
TRACK_Z = 6.0            # printed track height, mm
LET_W = 232.0            # wordmark width, mm
LET_CY = 327.0           # wordmark centre, mm from top
LET_Z = 6.0
RED = '#e3161f'
GUIDE_INSET = 0.4        # printed guides are this much smaller per side than the 3D parts, mm

# ---------------- track ----------------
race = json.load(open(os.path.join(D, 'raceway.json')))['elements']
DROP_IDS = {189535481, 638329117}   # pit-entry link and Bico de Pato shortcut
def keep(e):
    t = e['tags']
    return t.get('sport') == 'motor' and t.get('name') != 'Pit Lane' and e['id'] not in DROP_IDS
tways = [e for e in race if keep(e)]
lat = np.array([p['lat'] for e in tways for p in e['geometry']])
lon = np.array([p['lon'] for e in tways for p in e['geometry']])
lat0, lon0 = lat.max(), (lon.min() + lon.max()) / 2
R = 6371008.8
kx = np.cos(np.radians((lat.min() + lat.max()) / 2))
def proj(g):
    lo = np.array([p['lon'] for p in g]); la = np.array([p['lat'] for p in g])
    x = W / 2 + np.radians(lo - lon0) * R * kx / SCALE * 1000
    y = TRACK_TOP + TRACK_W / 2 + np.radians(lat0 - la) * R / SCALE * 1000
    return np.column_stack([x, y])

lines = [LineString(proj(e['geometry'])) for e in tways]
track = unary_union([l.buffer(TRACK_W / 2, resolution=16) for l in lines])
track = track.buffer(0.25).buffer(-0.25)                       # close hairline gaps
def fill_small_holes(p, amin=1.5):
    return Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area > amin])
if isinstance(track, MultiPolygon):
    parts = sorted(track.geoms, key=lambda g: -g.area)
    print('track pieces:', [round(g.area, 1) for g in parts])
    track = MultiPolygon([fill_small_holes(g) for g in parts if g.area > 5])
else:
    track = fill_small_holes(track)
print('track bbox mm', [round(v, 1) for v in track.bounds], 'type', track.geom_type)

# ---------------- letters (traced from the official logo raster) ----------------
from PIL import Image, ImageFilter
import contourpy
UP = 12
al = Image.open(os.path.join(D, 'interlagos_logo.png')).getchannel('A').crop((183, 28, 500, 77))
al = al.resize((al.width * UP, al.height * UP), Image.BICUBIC).filter(ImageFilter.GaussianBlur(UP * 0.45))
z = np.asarray(al, float) / 255
z = np.pad(z, 2)
cg = contourpy.contour_generator(z=z, name='serial', line_type='Separate')
rings = [Polygon(l / UP).buffer(0) for l in cg.lines(0.5) if len(l) > 8]
rings = [r for r in rings if r.area > 0.3]
letters = None
for r in sorted(rings, key=lambda r: -r.area):                # even-odd fill
    letters = r if letters is None else letters.symmetric_difference(r)
letters = letters.buffer(0.12).buffer(-0.24).buffer(0.12).simplify(0.03)   # smooth pixel wobble
b = letters.bounds; s = LET_W / (b[2] - b[0])
letters = affinity.scale(letters, s, s, origin=(0, 0))
b = letters.bounds
letters = affinity.translate(letters, W / 2 - (b[0] + b[2]) / 2, LET_CY - (b[1] + b[3]) / 2)
print('letters bbox mm', [round(v, 1) for v in letters.bounds], 'pieces', len(getattr(letters, 'geoms', [letters])))

# ---------------- STL ----------------
def to_stl(geom, z, fn):
    geom = affinity.scale(geom, 1, -1, origin=(0, H / 2))     # page y-down -> model y-up
    polys = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]
    m = trimesh.util.concatenate([trimesh.creation.extrude_polygon(p, z) for p in polys])
    m.export(os.path.join(HERE, fn))
    print(fn, 'size mm', np.round(m.extents, 1), 'watertight', all(x.is_watertight for x in m.split(only_watertight=False)), 'bodies', len(polys))
to_stl(track, TRACK_Z, 'track.stl')
to_stl(letters, LET_Z, 'letters.stl')

# ---------------- background ----------------
els = json.load(open(os.path.join(D, 'map.json')))['elements']
MAJOR = {'motorway': 0, 'trunk': 0, 'primary': 0, 'motorway_link': 1, 'trunk_link': 1, 'primary_link': 1,
         'secondary': 1, 'secondary_link': 1, 'tertiary': 2, 'tertiary_link': 2,
         'unclassified': 3, 'residential': 3, 'living_street': 3, 'pedestrian': 3,
         'service': 4, 'raceway': 4, 'track': 5, 'path': 6, 'footway': 6, 'cycleway': 6, 'bridleway': 6, 'steps': 6}
roads = {i: [] for i in range(7)}; bld = []; water_l = []; water_p = []; rail = []
for e in els:
    g = e.get('geometry'); t = e.get('tags', {})
    if not g: continue
    xy = proj(g)
    if xy[:, 0].max() < -5 or xy[:, 0].min() > W + 5 or xy[:, 1].max() < -5 or xy[:, 1].min() > H + 5: continue
    if 'highway' in t:
        c = MAJOR.get(t['highway'])
        if c is not None and t.get('area') != 'yes': roads[c].append(xy)
    elif 'building' in t and len(xy) > 3: bld.append(xy)
    elif t.get('natural') == 'water' and len(xy) > 3: water_p.append(xy)
    elif t.get('waterway') in ('river', 'stream', 'canal'): water_l.append(xy)
    elif t.get('railway') in ('rail', 'light_rail', 'narrow_gauge'): rail.append(xy)
print({k: len(v) for k, v in roads.items()}, 'bld', len(bld), 'water', len(water_l), len(water_p))

MM = 72 / 25.4
THEMES = {
    'dark':  dict(bg='#0b0b0b', bld='#3a3a3a', water='#2c2c2c', rail='#555555', halo='#0b0b0b',
                  road=['#ffffff', '#f2f2f2', '#dcdcdc', '#b4b4b4', '#8a8a8a', '#6a6a6a', '#4c4c4c']),
    'light': dict(bg='#f7f7f7', bld='#bdbdbd', water='#cfcfcf', rail='#909090', halo='#f7f7f7',
                  road=['#000000', '#101010', '#262626', '#4a4a4a', '#707070', '#8c8c8c', '#a8a8a8']),
}
RW = [1.3, 1.1, 0.85, 0.55, 0.3, 0.25, 0.18]                 # line widths, mm

def geom_patch(geom, **kw):
    verts, codes = [], []
    for p in (geom.geoms if hasattr(geom, 'geoms') else [geom]):
        for ring in [p.exterior, *p.interiors]:
            c = np.asarray(ring.coords)
            verts += c.tolist(); codes += [Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY]
    return PathPatch(Path(verts, codes), **kw)

def smooth(a, b, x): t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def fade_rgba(px=4):
    x = (np.arange(int(W * px)) + .5) / px; y = (np.arange(int(H * px)) + .5) / px
    X, Y = np.meshgrid(x, y)
    vis = smooth(5, 52, X) * smooth(5, 52, W - X) * smooth(4, 40, Y) * (0.12 + 0.88 * smooth(15, 175, H - Y)) * smooth(4, 30, H - Y)
    img = np.zeros(X.shape + (4,)); img[..., 3] = 1 - vis
    return img

def render(theme, guides=True, suffix=''):
    T = THEMES[theme]
    fig = plt.figure(figsize=(W / 25.4, H / 25.4)); ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis('off'); fig.patch.set_facecolor(T['bg'])
    ax.add_collection(PolyCollection(water_p, facecolors=T['water'], edgecolors='none', zorder=1))
    ax.add_collection(LineCollection(water_l, colors=T['water'], linewidths=0.3 * MM, zorder=1, capstyle='round'))
    ax.add_collection(PolyCollection(bld, facecolors=T['bld'], edgecolors='none', zorder=2))
    ax.add_collection(LineCollection(rail, colors=T['rail'], linewidths=0.25 * MM, linestyles=(0, (4, 2)), zorder=3))
    for c in range(6, -1, -1):
        ax.add_collection(LineCollection(roads[c], colors=T['road'][c], linewidths=RW[c] * MM, zorder=10 - c,
                                         capstyle='round', joinstyle='round'))
    ax.imshow(fade_rgba(), extent=(0, W, H, 0), zorder=20, interpolation='bilinear', aspect='auto')
    if guides:
        ax.add_patch(geom_patch(track.buffer(0.7), facecolor=T['halo'], edgecolor='none', zorder=21))
        ax.add_patch(geom_patch(track.buffer(-GUIDE_INSET), facecolor=RED, edgecolor='none', zorder=22))
        ax.add_patch(geom_patch(letters.buffer(-GUIDE_INSET), facecolor=RED, edgecolor='none', zorder=22))
    base = os.path.join(HERE, f'background_A3_{theme}{suffix}')
    fig.savefig(base + '.pdf', facecolor=T['bg'])
    fig.savefig(base + '.png', dpi=300, facecolor=T['bg'])
    fig.savefig(base + '_preview.png', dpi=45, facecolor=T['bg'])
    plt.close(fig)

render('dark')

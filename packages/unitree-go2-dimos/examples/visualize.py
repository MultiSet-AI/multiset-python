"""All seven steps, ending in a picture.

    pip install 'multiset-unitree-go2-dimos[viz]'
    python examples/visualize.py --mesh map.glb

    1. read GO2_IP and the MultiSet credentials from .env
    2. (done once beforehand: go2-credentials --save)
    3. connect to the robot
    4. open the camera
    5. capture a frame and undistort it
    6. ask VPS where that frame was taken
    7. convert the answer from the camera's Y-up frame to base_link, Z-up

...then draws the robot on your map mesh, with a marker at every fix.

Kept deliberately small. It is an example, not a product: a static view, no
walking model and no video. The library does not import open3d -- only this
file does.
"""

from __future__ import annotations

import argparse
import logging
import math
import time

import numpy as np
from multiset.unitree.go2.dimos import Go2, Go2Error, VizNotInstalled

log = logging.getLogger("visualize")

ROBOT_COLOR = (0.20, 0.70, 0.95)
FIX_COLOR = (1.00, 0.25, 0.85)
HEADING_COLOR = (0.95, 0.15, 0.12)


def _open3d():
    """Import open3d, or explain how to get it."""
    try:
        import open3d as o3d
    except ImportError as exc:
        raise VizNotInstalled from exc
    return o3d


def load_map(o3d, path, centre, span: float):
    """The map mesh, in the Z-up frame the poses are in, cropped around the robot.

    Two things worth knowing, both learned the hard way:

    The mesh arrives in the SAME Y-up frame as a VPS pose, so it gets the same
    conversion. Rotate one and not the other and everything still renders --
    the robot is simply standing in a different room from the one on screen.

    The ceiling is cut away. Looking down at a room whose roof is intact shows
    a grey slab, so the height cut is what makes the interior visible at all.
    """
    from multiset.vps import YUP_TO_ZUP

    mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=True)
    if len(mesh.vertices) == 0:
        raise Go2Error(f"{path} loaded but contains no geometry")
    mesh.transform(YUP_TO_ZUP)

    # Crop by triangle index rather than mesh.crop(): crop() discards the
    # texture coordinates, and a map that loses its UVs renders flat grey.
    V = np.asarray(mesh.vertices)
    T = np.asarray(mesh.triangles)
    centroids = V[T].mean(axis=1)
    keep = (
        (np.abs(centroids[:, 0] - centre[0]) <= span)
        & (np.abs(centroids[:, 1] - centre[1]) <= span)
        & (centroids[:, 2] >= -1.5)
        & (centroids[:, 2] <= 1.1)
    )
    if not keep.any():
        log.warning("nothing within %.0f m of the robot; showing the whole map", span)
        return mesh

    sub = o3d.geometry.TriangleMesh(mesh.vertices, o3d.utility.Vector3iVector(T[keep]))
    uvs = np.asarray(mesh.triangle_uvs)
    if len(uvs) == 3 * len(T):
        kept_uvs = uvs.reshape(-1, 3, 2)[keep].reshape(-1, 2)
        sub.triangle_uvs = o3d.utility.Vector2dVector(kept_uvs)
        sub.textures = mesh.textures
        ids = np.asarray(mesh.triangle_material_ids)
        if len(ids) == len(T):
            sub.triangle_material_ids = o3d.utility.IntVector(ids[keep].astype(np.int32))
    sub.compute_vertex_normals()
    log.info("map: %d -> %d triangles after cropping", len(T), len(sub.triangles))
    return sub


def robot_marker(o3d, x: float, y: float, yaw_deg: float):
    """A box the size of a Go2, plus an arrow showing which way it faces.

    A box, not the real Unitree model: fetching and posing 398k triangles is a
    lot of machinery for an example. The heading arrow matters more than the
    shape -- a pose that is right in position and wrong in heading looks
    entirely correct in a screenshot.
    """
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    T = np.eye(4)
    T[:3, :3] = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    # base_link sits ~0.32 m above the feet; without the lift the robot renders
    # buried to its belly in the floor.
    T[:3, 3] = (x, y, 0.32)

    body = o3d.geometry.TriangleMesh.create_box(0.70, 0.31, 0.30)
    body.translate((-0.35, -0.155, -0.15))
    body.transform(T)
    body.paint_uniform_color(ROBOT_COLOR)
    body.compute_vertex_normals()

    arrow = o3d.geometry.TriangleMesh.create_arrow(
        cylinder_radius=0.012, cone_radius=0.030, cylinder_height=0.28, cone_height=0.10
    )
    arrow.rotate(
        o3d.geometry.get_rotation_matrix_from_axis_angle([0, math.pi / 2, 0]), center=(0, 0, 0)
    )
    arrow.translate((0.05, 0.0, 0.28))
    arrow.transform(T)
    arrow.paint_uniform_color(HEADING_COLOR)
    arrow.compute_vertex_normals()
    return [body, arrow]


def fix_marker(o3d, x: float, y: float):
    sphere = o3d.geometry.TriangleMesh.create_sphere(0.07, resolution=10)
    sphere.translate((x, y, 0.10))
    sphere.paint_uniform_color(FIX_COLOR)
    sphere.compute_vertex_normals()
    return sphere


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", required=True, help="your map mesh (.glb / .ply)")
    parser.add_argument("--count", type=int, default=1, help="how many fixes to take")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between fixes")
    parser.add_argument("--crop", type=float, default=8.0, help="metres of map to show")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    o3d = _open3d()
    geometries = []
    latest = None

    # Steps 1, 3, 4 -- .env, connect, camera. One context manager.
    with Go2.from_env() as dog:
        for i in range(args.count):
            if i:
                time.sleep(args.interval)
            # Steps 5, 6, 7 -- capture + undistort, query, and the conversion
            # from the camera's Y-up pose to base_link in Z-up.
            base = dog.base_pose()
            if base is None:
                # Not an error: a featureless wall legitimately does not match.
                print(f"{i + 1}/{args.count}  no pose")
                continue
            x, y, yaw = base
            latest = base
            print(f"{i + 1}/{args.count}  base_link ({x:+.3f}, {y:+.3f})  yaw {yaw:+.1f}deg")
            geometries.append(fix_marker(o3d, x, y))

    if latest is None:
        print("\nnothing localized -- point the robot at something with more structure")
        return 2

    x, y, yaw = latest
    geometries = [
        load_map(o3d, args.mesh, (x, y), args.crop),
        *robot_marker(o3d, x, y, yaw),
        *geometries,
    ]
    print(f"\nshowing {len(geometries)} geometries; close the window to exit")
    o3d.visualization.draw_geometries(geometries, window_name="multiset-unitree-go2-dimos")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Go2Error as exc:
        print(f"error: {exc}")
        raise SystemExit(1) from exc

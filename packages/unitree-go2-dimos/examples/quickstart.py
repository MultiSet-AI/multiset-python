"""Connect, localize, print a pose.

    python examples/quickstart.py

Needs .env with GO2_IP, GO2_AES_KEY and the three MULTISET_* values.
"""

import logging
import math

from multiset.unitree.go2.dimos import Go2, camera_pose_to_base
from multiset.vps import MultisetError

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> int:
    try:
        with Go2.from_env() as dog:
            pose = dog.localize()
            if not pose:
                # Not an error: a featureless wall legitimately fails to match.
                print("no pose -- point the robot somewhere with more structure")
                return 2
            print(f"camera   : {pose}")
            # Convert the pose we already have. dog.base_pose() would localize
            # again -- a second query, and a second, different frame.
            T = camera_pose_to_base(pose.matrix)
            yaw = math.degrees(math.atan2(T[1, 0], T[0, 0]))
            print(f"base_link: ({T[0, 3]:+.3f}, {T[1, 3]:+.3f})  yaw {yaw:+.1f}deg")
    except MultisetError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

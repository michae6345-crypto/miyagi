"""Start the miyagi bridge in a Blender that does not have it installed.

    <blender> /abs/lesson.blend --python <repo>/blender-addon/start_bridge.py

Puts this folder on sys.path, imports miyagi_bridge and calls register(): the loopback server and its timer run
until Blender quits. It draws nothing and changes nothing in the scene.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import miyagi_bridge

miyagi_bridge.register()

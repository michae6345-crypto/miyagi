"""python -m server.evals.links [-v] [-k ID] [--json] [--write-baseline]"""
import sys

from .runner import main

sys.exit(main())

"""python -m server.evals.checks [-v] [-k ID] [--json] [--write-baseline]"""
import sys

from .runner import main

sys.exit(main())

"""Download db-ip.com's free "IP to Country Lite" database for the region block (COUNTRY_DB_PATH).

    python scripts/fetch_country_db.py /var/data/dbip-country-lite.csv.gz          # this month's file
    python scripts/fetch_country_db.py /var/data/dbip-country-lite.csv.gz 2026-11  # a given month

Run it by hand (or from a monthly job), never per request: it is the one outside call the region block makes, and
the proxy only reads the file it leaves behind, at startup. db-ip.com publishes a new file at the start of each month.

License: IP to Country Lite by DB-IP (https://db-ip.com), CC BY 4.0. The attribution "IP Geolocation by DB-IP" with a
link to https://db-ip.com goes on a public page (the privacy policy's region line is a good place).

Size: about 4-5 MB gzipped (about 25 MB as CSV), a few hundred thousand IPv4 and IPv6 ranges. The proxy reads the .gz
directly. The file is checked (it must parse, with at least MIN_RANGES ranges and a US range for 8.8.8.8) before it
replaces the old one, so a bad download never takes the block's database away; restart the service to load it.
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geo  # noqa: E402

URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.csv.gz"
MIN_RANGES = 100_000


def main(dest: str, month: str | None = None) -> int:
    month = month or datetime.now(UTC).strftime("%Y-%m")
    url = URL.format(month=month)
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".csv.gz")
    os.close(fd)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "miyagi-cloud-country-db"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        db = geo.CountryDB.load(tmp)
        if db.rows < MIN_RANGES or db.lookup("8.8.8.8") != "US":
            print(f"refused: {url} parsed to {db.rows} ranges", file=sys.stderr)
            return 1
        os.replace(tmp, out)
        print(f"{out}: {db.rows} ranges ({len(db)} merged) from {url}")
        return 0
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))

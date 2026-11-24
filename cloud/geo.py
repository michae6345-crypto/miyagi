"""Country of a client IP for the region block (REGION_BLOCK, decision D9), offline and in memory.

Two sources, both optional, never an outside call per request:

  * a header the edge sets (COUNTRY_HEADER, e.g. cf-ipcountry once Cloudflare is in front of the service: R12).
    Render documents no country header, so it is off by default; only set it for a header the edge overwrites,
    since a client that reaches the origin can send any header it likes;
  * an IP-to-country database file (COUNTRY_DB_PATH) in db-ip.com's "IP to Country Lite" CSV format
    (`first_ip,last_ip,country_code`, IPv4 and IPv6, optionally .gz), licensed CC BY 4.0 by db-ip.com: see
    scripts/fetch_country_db.py and README "Region block" for where it comes from and how to refresh it.

The country is only ever returned to the caller: nothing here stores or logs an address or a country.
"""

from __future__ import annotations

import csv
import gzip
import io
import ipaddress
import re
from array import array
from bisect import bisect_right

_CC = re.compile(r"[A-Z]{2}")
# Not countries: Cloudflare's XX (unknown) and T1 (Tor), db-ip's ZZ (reserved), EU / AP (continent placeholders)
NOT_COUNTRIES = frozenset({"XX", "T1", "ZZ", "EU", "AP"})


def country_code(raw) -> str | None:
    """A two-letter ISO country code, upper case, or None."""
    if not isinstance(raw, str):
        return None
    cc = raw.strip().upper()
    return cc if _CC.fullmatch(cc) and cc not in NOT_COUNTRIES else None


class CountryDB:
    """Sorted, merged ranges per IP version; lookup is a binary search. A db-ip country lite file (about 600k rows,
    about 25 MB as CSV) merges to fewer ranges and takes some tens of MB in memory."""

    def __init__(self) -> None:
        self._v4_start, self._v4_end, self._v4_cc = array("L"), array("L"), []
        self._v6_start: list[int] = []
        self._v6_end: list[int] = []
        self._v6_cc: list[str] = []
        self.rows = 0

    @classmethod
    def load(cls, path: str) -> "CountryDB":
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", newline="") as f:
            return cls.from_rows(csv.reader(f))

    @classmethod
    def from_text(cls, text: str) -> "CountryDB":
        return cls.from_rows(csv.reader(io.StringIO(text)))

    @classmethod
    def from_rows(cls, rows) -> "CountryDB":
        db = cls()
        v4: list[tuple[int, int, str]] = []
        v6: list[tuple[int, int, str]] = []
        for row in rows:
            if len(row) < 3:
                continue
            cc = country_code(row[2])
            if cc is None:
                continue
            try:
                a, b = ipaddress.ip_address(row[0].strip()), ipaddress.ip_address(row[1].strip())
            except ValueError:
                continue  # a header line or a bad row
            if a.version != b.version or int(b) < int(a):
                continue
            (v4 if a.version == 4 else v6).append((int(a), int(b), cc))
            db.rows += 1
        sys_cc: dict[str, str] = {}  # one string object per country code
        for ranges, starts, ends, ccs in ((v4, db._v4_start, db._v4_end, db._v4_cc), (v6, db._v6_start, db._v6_end, db._v6_cc)):
            ranges.sort()
            for a, b, cc in ranges:
                cc = sys_cc.setdefault(cc, cc)
                if ccs and ccs[-1] == cc and a <= ends[-1] + 1:  # adjacent or overlapping, same country: merge
                    ends[-1] = max(ends[-1], b)
                    continue
                if ends and a <= ends[-1]:  # overlaps a different country: keep the earlier range's claim
                    a = ends[-1] + 1
                    if a > b:
                        continue
                starts.append(a)
                ends.append(b)
                ccs.append(cc)
        return db

    def __len__(self) -> int:
        return len(self._v4_cc) + len(self._v6_cc)

    def lookup(self, ip: str) -> str | None:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        n = int(a)
        if a.version == 4:
            starts, ends, ccs = self._v4_start, self._v4_end, self._v4_cc
        else:
            starts, ends, ccs = self._v6_start, self._v6_end, self._v6_cc
        i = bisect_right(starts, n) - 1
        return ccs[i] if i >= 0 and n <= ends[i] else None


# D9 (adrian/launch-risk research/launch/SOLUTIONS.md): "US first; block the EEA, UK, Switzerland and Anthropic's
# unsupported regions at the proxy; revisit with an entity".
EEA = ("AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT",
       "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",  # the EU 27
       "IS", "LI", "NO",  # + EEA
       "AX", "GF", "GP", "MQ", "RE", "YT", "MF")  # EU territory with its own ISO code (Åland, the outermost regions)
UK_CH = ("GB", "CH")
# Not on Anthropic's supported-countries list (anthropic.com/supported-countries, read 2026-11-24: "Any country or region
# not listed is unsupported"): the sovereign states and the two Chinese SARs it leaves out, plus Kosovo. The excluded
# Ukrainian regions (Crimea, Donetsk, Kherson, Luhansk, Zaporizhzhia) have no ISO code of their own and cannot be
# blocked by country; dependent territories absent from the list are not blocked by default (add them if needed).
ANTHROPIC_UNSUPPORTED = ("AF", "BY", "CN", "CU", "IR", "KP", "MM", "RU", "SY", "VE", "YE", "HK", "MO", "XK")
DEFAULT_BLOCKED = ",".join(EEA + UK_CH + ANTHROPIC_UNSUPPORTED)

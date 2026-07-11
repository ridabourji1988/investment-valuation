"""ESEF filings (filings.xbrl.org) — EU-only filers, keyless.

European listed companies file audited annual reports as ESEF (Inline XBRL);
filings.xbrl.org republishes them as xBRL-JSON (OIM). This module adapts those
facts into the exact EDGAR-companyfacts shape, so the whole live.py assembly —
tag fallbacks, filed-value identities, forensic scores — works on EU filings
unchanged.

Recipe (validated live 2026-07-11, PROJECT/PLAN.md Milestone 2):
- filings per entity: /api/entities/{LEI}/filings (relationship filters on
  /api/filings silently return 0). json_url is root-relative and can be null;
  amended (fxo_id /0,/1) and language-variant filings share a period_end.
- facts: keep only facts whose dimensions have NO keys beyond
  {concept, entity, period, unit, language} — consolidated, undimensioned.
- OIM periods are datetimes with an exclusive end (midnight AFTER the last
  day): FY2024 = "2024-01-01T00:00:00/2025-01-01T00:00:00", the matching
  balance-sheet instant is "2025-01-01T00:00:00" — both map to end 2024-12-31.

Germany does NOT feed filings.xbrl.org (BMW/Siemens are not coverable here);
coverage is strong for FR/NL/FI/DK/GB. The registry below is curated:
non-financial, EUR-reporting large caps with a Euronext/Nasdaq-Helsinki
listing Yahoo can price (banks/insurers excluded — FCFF misvalues them).
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse

from .cache import get_cached, http_get

_BASE = "https://filings.xbrl.org"
_GLEIF = "https://api.gleif.org/api/v1/lei-records"
_UA = {"User-Agent": "ValueScope research contact@example.com"}
_TTL = 12 * 3600

# Yahoo listing ticker -> entity. Every LEI verified live against GLEIF and
# filings.xbrl.org on 2026-07-11 (usable = json_url present, period ended).
# Where the company name failed on GLEIF fulltext, the LEI was resolved by
# ISIN (filter[isin]=...) — that finds the operating entity directly.
_PA, _AS, _HE = "Euronext Paris", "Euronext Amsterdam", "Nasdaq Helsinki"
REGISTRY: dict = {
    "MC.PA": {"lei": "IOG4E947OATN0KJYSD45", "name": "LVMH Moët Hennessy Louis Vuitton",
              "sector": "Luxury goods", "exchange": _PA},
    "RMS.PA": {"lei": "969500Y4IJGHJE2MTJ13", "name": "Hermès International",
               "sector": "Luxury goods", "exchange": _PA},
    "OR.PA": {"lei": "529900JI1GG6F7RKVI53", "name": "L'Oréal",
              "sector": "Personal care", "exchange": _PA},
    "AIR.PA": {"lei": "MINO79WLOO247M1IL051", "name": "Airbus",
               "sector": "Aerospace & defense", "exchange": _PA},
    "SU.PA": {"lei": "969500A1YF1XUYYXS284", "name": "Schneider Electric",
              "sector": "Electrical equipment", "exchange": _PA},
    "KER.PA": {"lei": "549300VGEJKB7SVUZR78", "name": "Kering",
               "sector": "Luxury goods", "exchange": _PA},
    "DSY.PA": {"lei": "96950065LBWY0APQIM86", "name": "Dassault Systèmes",
               "sector": "Software", "exchange": _PA},
    "EL.PA": {"lei": "549300M3VH1A3ER1TB49", "name": "EssilorLuxottica",
              "sector": "Eyewear & med-tech", "exchange": _PA},
    "ML.PA": {"lei": "549300SOSI58J6VIW052", "name": "Michelin",
              "sector": "Tires", "exchange": _PA},
    "RI.PA": {"lei": "52990097YFPX9J0H5D87", "name": "Pernod Ricard",
              "sector": "Beverages", "exchange": _PA},
    "AF.PA": {"lei": "969500AQW31GYO8JZD66", "name": "Air France-KLM",
              "sector": "Airlines", "exchange": _PA},
    "AI.PA": {"lei": "969500MMPQVHK671GT54", "name": "Air Liquide",
              "sector": "Industrial gases", "exchange": _PA},
    "SAF.PA": {"lei": "969500UIC89GT3UL7L24", "name": "Safran",
               "sector": "Aerospace & defense", "exchange": _PA},
    "DG.PA": {"lei": "213800WFQ334R8UXUG83", "name": "Vinci",
              "sector": "Construction & concessions", "exchange": _PA},
    "BN.PA": {"lei": "969500KMUQ2B6CBAF162", "name": "Danone",
              "sector": "Food & dairy", "exchange": _PA},
    "HO.PA": {"lei": "529900FNDVTQJOVVPZ19", "name": "Thales",
              "sector": "Aerospace & defense", "exchange": _PA},
    "SGO.PA": {"lei": "NFONVGN05Z0FMN5PEC35", "name": "Saint-Gobain",
               "sector": "Building materials", "exchange": _PA},
    "LR.PA": {"lei": "969500XXRPGD7HCAFA90", "name": "Legrand",
              "sector": "Electrical equipment", "exchange": _PA},
    "CAP.PA": {"lei": "96950077L0TN7BAROX36", "name": "Capgemini",
               "sector": "IT services", "exchange": _PA},
    "PUB.PA": {"lei": "2138004KW8BV57III342", "name": "Publicis Groupe",
               "sector": "Advertising", "exchange": _PA},
    "ORA.PA": {"lei": "969500MCOONR8990S771", "name": "Orange",
               "sector": "Telecom", "exchange": _PA},
    "VIE.PA": {"lei": "969500LENY69X51OOT31", "name": "Veolia",
               "sector": "Water & waste", "exchange": _PA},
    "SW.PA": {"lei": "969500LCBOG12HXPYM84", "name": "Sodexo",
              "sector": "Food services", "exchange": _PA},
    "AC.PA": {"lei": "969500QZC2Q0TK11NV07", "name": "Accor",
              "sector": "Hotels", "exchange": _PA},
    "CA.PA": {"lei": "549300B8P6MUJ1YWTS08", "name": "Carrefour",
              "sector": "Food retail", "exchange": _PA},
    "BVI.PA": {"lei": "969500TPU5T3HA5D1F11", "name": "Bureau Veritas",
               "sector": "Testing & certification", "exchange": _PA},
    "ENGI.PA": {"lei": "LAXUQCHT4FH58LRZDY46", "name": "Engie",
                "sector": "Utilities", "exchange": _PA},
    "TEP.PA": {"lei": "9695004GI61FHFFNRG61", "name": "Teleperformance",
               "sector": "Customer experience & BPO", "exchange": _PA},
    "EDEN.PA": {"lei": "9695006LOD5B2D7Y0N70", "name": "Edenred",
                "sector": "Payments & benefits", "exchange": _PA},
    "ERF.PA": {"lei": "529900JEHFM47DYY3S57", "name": "Eurofins Scientific",
               "sector": "Laboratory testing", "exchange": _PA},
    "ADYEN.AS": {"lei": "724500973ODKK3IFQ447", "name": "Adyen",
                 "sector": "Payments", "exchange": _AS},
    "HEIA.AS": {"lei": "724500K5PTPSST86UQ23", "name": "Heineken",
                "sector": "Beverages (brewing)", "exchange": _AS},
    "AKZA.AS": {"lei": "724500XYIJUGXAA5QD70", "name": "Akzo Nobel",
                "sector": "Paints & coatings", "exchange": _AS},
    "RAND.AS": {"lei": "7245009EAAUUQJ0U4T57", "name": "Randstad",
                "sector": "Staffing", "exchange": _AS},
    "JDEP.AS": {"lei": "724500EHG519SE5ZRT89", "name": "JDE Peet's",
                "sector": "Coffee & tea", "exchange": _AS},
    "UMG.AS": {"lei": "724500GJBUL3D9TW9Y18", "name": "Universal Music Group",
               "sector": "Music & entertainment", "exchange": _AS},
    "ASM.AS": {"lei": "7245001I22ND6ZFHX623", "name": "ASM International",
               "sector": "Semiconductor equipment", "exchange": _AS},
    "WKL.AS": {"lei": "724500TEM53I0U077B74", "name": "Wolters Kluwer",
               "sector": "Information services", "exchange": _AS},
    "AD.AS": {"lei": "724500C9GNBV20UYRX36", "name": "Ahold Delhaize",
              "sector": "Food retail", "exchange": _AS},
    "KNEBV.HE": {"lei": "2138001CNF45JP5XZK38", "name": "KONE",
                 "sector": "Elevators & escalators", "exchange": _HE},
    "NESTE.HE": {"lei": "5493009GY1X8GQ66AM14", "name": "Neste",
                 "sector": "Refining & renewable fuels", "exchange": _HE},
    "UPM.HE": {"lei": "213800EC6PW5VU4J9U64", "name": "UPM-Kymmene",
               "sector": "Forest products", "exchange": _HE},
}


def in_registry(ticker: str) -> bool:
    return ticker.upper() in REGISTRY


# --------------------------------------------------------------------------- #
# OIM -> EDGAR-shape adapter
# --------------------------------------------------------------------------- #
_CORE_DIMS = {"concept", "entity", "period", "unit", "language"}


def _iso_date(datetime_str: str, *, exclusive_end: bool) -> str | None:
    """OIM datetime -> filing-style date. Exclusive ends (durations' second
    half and instants) denote midnight after the last day -> subtract a day."""
    try:
        d = dt.datetime.fromisoformat(datetime_str.replace("Z", "")).date()
    except ValueError:
        return None
    if exclusive_end:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def _map_unit(unit: str | None) -> str | None:
    """iso4217:EUR -> EUR, xbrli:shares -> shares, EUR/shares kept as ratio."""
    if not unit:
        return None
    parts = [p.split(":")[-1] for p in unit.split("/")]
    return "/".join(parts)


def merge_oim(target: dict, oim: dict, *, filed: str) -> None:
    """Merge one xBRL-JSON document's consolidated facts into an
    EDGAR-companyfacts-shaped dict (facts.ifrs-full.<concept>.units.<unit>).
    Rows carry form="ESEF" so edgar._extract_rows accepts them."""
    facts = target.setdefault("facts", {})
    for fact in (oim.get("facts") or {}).values():
        dims = fact.get("dimensions") or {}
        if set(dims) - _CORE_DIMS:
            continue  # segment/axis breakdown — consolidated figures only
        concept = dims.get("concept") or ""
        if ":" not in concept:
            continue
        ns, name = concept.split(":", 1)
        if ns != "ifrs-full":
            continue  # extension taxonomies: no cross-filer meaning
        try:
            val = float(fact.get("value"))
        except (TypeError, ValueError):
            continue
        period = dims.get("period") or ""
        if "/" in period:
            start_s, end_s = period.split("/", 1)
            start = _iso_date(start_s, exclusive_end=False)
            end = _iso_date(end_s, exclusive_end=True)
        else:
            start, end = None, _iso_date(period, exclusive_end=True)
        if not end:
            continue
        unit = _map_unit(dims.get("unit"))
        if not unit:
            continue
        row = {"end": end, "val": val, "form": "ESEF", "filed": filed, "fy": end[:4]}
        if start:
            row["start"] = start
        rows = (facts.setdefault(ns, {}).setdefault(name, {})
                .setdefault("units", {}).setdefault(unit, []))
        # replace an identical (start, end) row only with a later filing
        for i, r in enumerate(rows):
            if r.get("start") == row.get("start") and r["end"] == end:
                if filed > r["filed"]:
                    rows[i] = row
                break
        else:
            rows.append(row)


# --------------------------------------------------------------------------- #
# filings.xbrl.org
# --------------------------------------------------------------------------- #
def _filings(lei: str) -> list[dict]:
    """Usable annual filings, newest first: json_url present, period ended,
    amended/language variants deduped by period_end (latest date_added wins)."""
    def build():
        url = f"{_BASE}/api/entities/{lei}/filings?page[size]=100"
        rows = http_get(url, headers=_UA, timeout=40).json().get("data", [])
        today = dt.date.today().isoformat()
        by_period: dict = {}
        for x in rows:
            a = x.get("attributes") or {}
            end, json_url = a.get("period_end") or "", a.get("json_url")
            if not json_url or not end or end > today:
                continue
            prev = by_period.get(end)
            if prev is None or str(a.get("date_added", "")) > str(prev.get("date_added", "")):
                by_period[end] = a
        return [by_period[end] for end in sorted(by_period, reverse=True)]
    return get_cached(f"esef:filings:{lei}", _TTL, build)


def company_facts(ticker: str, *, max_filings: int = 2) -> dict:
    """EDGAR-shaped consolidated facts from the newest ESEF filings. Two
    filings (each tagging current + prior year) give 3-4 fiscal years —
    enough for growth, margins and the two-year forensic scores.

    The adapted dict is what gets cached (a few hundred KB); the raw
    xBRL-JSON documents (5-15 MB each) are fetched only on cache miss."""
    meta = REGISTRY[ticker.upper()]
    lei = meta["lei"]

    def build():
        filings = _filings(lei)[:max_filings]
        if not filings:
            raise ValueError(f"{ticker}: no usable ESEF filings for LEI {lei}")
        out: dict = {"facts": {}}
        for f in filings:
            url = urllib.parse.urljoin(_BASE, f["json_url"])
            doc = json.loads(http_get(url, headers=_UA, timeout=90).content)
            merge_oim(out, doc, filed=str(f.get("date_added", ""))[:10])
        return out
    return get_cached(f"esef:facts:{lei}", _TTL, build)


def company_profile(ticker: str) -> dict:
    """Same shape as edgar.company_profile, with verify-at-source links into
    filings.xbrl.org (the filing directory holds the human-readable report)."""
    meta = REGISTRY[ticker.upper()]
    filings = _filings(meta["lei"])
    filing = None
    if filings:
        f = filings[0]
        doc_url = urllib.parse.urljoin(_BASE, f["json_url"])
        filing = {
            "form": "ESEF annual report",
            "filed": str(f.get("date_added", ""))[:10] or f.get("period_end"),
            "url": doc_url.rsplit("/", 1)[0] + "/",
        }
    return {
        "name": meta["name"], "exchange": meta["exchange"],
        "sector": meta["sector"], "cik": None, "lei": meta["lei"],
        "filing": filing,
    }


def source_links(ticker: str, *, price_source: str = "") -> dict:
    meta = REGISTRY[ticker.upper()]
    profile = company_profile(ticker)
    filings = _filings(meta["lei"])
    xbrl = (urllib.parse.urljoin(_BASE, filings[0]["json_url"]) if filings else None)
    if "Boursorama" in price_source:
        from . import boursorama
        prices = boursorama.quote_page_url(ticker)
    else:
        prices = f"https://finance.yahoo.com/quote/{ticker.upper()}"
    return {
        "filing": profile["filing"],
        "filings_index": f"{_BASE}/api/entities/{meta['lei']}/filings",
        "xbrl_data": xbrl,
        "prices": prices,
        "fx": None,
    }


def search(query: str, *, limit: int = 6) -> list[dict]:
    """Registry-first search; every hit is analyzable end-to-end."""
    q = query.strip().lower()
    if len(q) < 2:
        return []
    hits = []
    for ticker, meta in REGISTRY.items():
        if q in ticker.lower() or q in meta["name"].lower():
            hits.append({"ticker": ticker, "name": meta["name"],
                         "exchange": meta["exchange"], "source": "esef"})
    return hits[:limit]

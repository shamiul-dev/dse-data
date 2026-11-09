"""
Pure parser for DSE company fundamentals and profiles.
Employs robust, row-by-row DOM traversal that isolates row scopes.
"""

from datetime import date
from typing import Optional, Union
from lxml import html

from dse_scraper.core.normalizers import safe_date, safe_float, safe_int, safe_str
from dse_scraper.models.fundamentals import CompanyProfile


def parse_company_profile(raw_content: Union[str, bytes], symbol: str) -> CompanyProfile:
    """
    Parses company fundamentals from DSE profile HTML (legacy or modern).
    Uses row-scoped cell traversal to prevent bleeding across table rows.
    """
    if isinstance(raw_content, bytes):
        text = raw_content.decode("utf-8", errors="ignore")
    else:
        text = str(raw_content)

    if not text.strip():
        return CompanyProfile(symbol=symbol)

    try:
        doc = html.fromstring(text)
    except Exception:
        return CompanyProfile(symbol=symbol)

    profile = CompanyProfile(symbol=symbol)

    # 1. Company Name from headings
    # First: check for explicit 'Company Name:' label (legacy displayCompany format)
    for h in doc.xpath("//*[contains(text(), 'Company Name:')]"):
        clean = h.text_content().strip()
        if "Company Name:" in clean:
            name_part = clean.split("Company Name:", 1)[1].strip()
            if name_part:
                profile.name = name_part
                break

    # Second: check for top h1 heading (modern page or test mock format)
    if not profile.name:
        for h in doc.xpath("//h1"):
            clean = h.text_content().strip()
            if clean and clean not in ("Dhaka Stock Exchange", "Markets", "Companies"):
                profile.name = clean
                break

    # 2. Row-by-Row traversal
    for tr in doc.xpath("//tr"):
        cells = [cell.text_content().strip() for cell in tr.xpath("./td | ./th") if cell.text_content().strip()]
        if not cells:
            continue

        for i, cell in enumerate(cells):
            cell_lower = cell.lower()

            # Authorized Capital
            if "authorized capital" in cell_lower and i + 1 < len(cells):
                profile.authorized_capital = safe_float(cells[i + 1])

            # Paid-up Capital
            elif "paid-up capital" in cell_lower and i + 1 < len(cells):
                profile.paid_up_capital = safe_float(cells[i + 1])

            # Market Lot
            elif "market lot" in cell_lower and i + 1 < len(cells):
                profile.market_lot = safe_int(cells[i + 1], default=1)

            # Face Value
            elif "face/par value" in cell_lower or "face value" in cell_lower:
                if i + 1 < len(cells):
                    profile.face_value = safe_float(cells[i + 1])

            # Listing Year
            elif "listing year" in cell_lower and i + 1 < len(cells):
                profile.listing_year = safe_int(cells[i + 1])

            # Sector
            elif "sector" in cell_lower and i + 1 < len(cells) and not profile.sector:
                sec_candidate = safe_str(cells[i + 1])
                if sec_candidate and len(sec_candidate) > 2 and not sec_candidate.isdigit():
                    profile.sector = sec_candidate

            # P/E Ratio: extract the last valid numeric cell in this specific P/E row
            elif ("current p/e" in cell_lower or "p/e ratio" in cell_lower) and not profile.pe_ratio:
                for cand in reversed(cells[i + 1:]):
                    val = safe_float(cand)
                    if val is not None and 0.5 <= val <= 500:
                        profile.pe_ratio = val
                        break

            # EPS
            elif "basic eps" in cell_lower and not profile.eps:
                for cand in reversed(cells[i + 1:]):
                    val = safe_float(cand)
                    if val is not None:
                        profile.eps = val
                        break

            # NAV
            elif "nav per share" in cell_lower and not profile.nav_per_share:
                for cand in reversed(cells[i + 1:]):
                    val = safe_float(cand)
                    if val is not None:
                        profile.nav_per_share = val
                        break

            # Shareholding distribution
            elif "sponsor/director" in cell_lower and i + 1 < len(cells):
                profile.shareholding_sponsor = safe_float(cells[i + 1])
            elif "govt:" in cell_lower and i + 1 < len(cells):
                profile.shareholding_govt = safe_float(cells[i + 1])
            elif "institute:" in cell_lower and i + 1 < len(cells):
                profile.shareholding_institute = safe_float(cells[i + 1])
            elif "foreign:" in cell_lower and i + 1 < len(cells):
                profile.shareholding_foreign = safe_float(cells[i + 1])
            elif "public:" in cell_lower and i + 1 < len(cells):
                profile.shareholding_public = safe_float(cells[i + 1])

    return profile

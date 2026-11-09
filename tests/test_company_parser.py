from pathlib import Path
from dse_scraper.parsers.company_parser import parse_company_profile


def test_parse_company_profile_mock():
    html_mock = """
    <html>
        <h1>Grameenphone Ltd.</h1>
        <table>
            <tr><td>Authorized Capital (mn)</td><td>40,000.00</td></tr>
            <tr><td>Paid-up Capital (mn)</td><td>13,503.00</td></tr>
            <tr><td>Market Lot</td><td>1</td></tr>
            <tr><td>Face/par Value</td><td>10.0</td></tr>
            <tr><td>Listing Year</td><td>2009</td></tr>
            <tr><td>Sector</td><td>Telecommunication</td></tr>
            <tr><td>Current P/E Ratio using Basic EPS</td><td>10.49</td></tr>
            <tr>
                <td>Sponsor/Director:</td><td>90.00</td>
                <td>Govt:</td><td>0.00</td>
                <td>Institute:</td><td>6.63</td>
                <td>Foreign:</td><td>0.80</td>
                <td>Public:</td><td>2.57</td>
            </tr>
        </table>
    </html>
    """
    profile = parse_company_profile(html_mock, symbol="GP")

    assert profile.symbol == "GP"
    assert profile.authorized_capital == 40000.0
    assert profile.paid_up_capital == 13503.0
    assert profile.market_lot == 1
    assert profile.face_value == 10.0
    assert profile.listing_year == 2009
    assert profile.sector == "Telecommunication"
    assert profile.pe_ratio == 10.49
    assert profile.shareholding_sponsor == 90.0
    assert profile.shareholding_govt == 0.0
    assert profile.shareholding_institute == 6.63
    assert profile.shareholding_foreign == 0.80
    assert profile.shareholding_public == 2.57


def test_parse_company_profile_corrupt():
    profile = parse_company_profile("", symbol="CORRUPT")
    assert profile.symbol == "CORRUPT"
    assert profile.authorized_capital is None
    assert profile.pe_ratio is None


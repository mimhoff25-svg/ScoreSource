import os
import requests
from pathlib import Path

NBA_TEAM_IDS = {
    "ATL": "1610612737",
    "BOS": "1610612738",
    "BKN": "1610612751",
    "CHA": "1610612766",
    "CHI": "1610612741",
    "CLE": "1610612739",
    "DAL": "1610612742",
    "DEN": "1610612743",
    "DET": "1610612765",
    "GSW": "1610612744",
    "HOU": "1610612745",
    "IND": "1610612754",
    "LAC": "1610612746",
    "LAL": "1610612747",
    "MEM": "1610612763",
    "MIA": "1610612748",
    "MIL": "1610612749",
    "MIN": "1610612750",
    "NOP": "1610612740",
    "NYK": "1610612752",
    "OKC": "1610612760",
    "ORL": "1610612753",
    "PHI": "1610612755",
    "PHX": "1610612756",
    "POR": "1610612757",
    "SAC": "1610612758",
    "SAS": "1610612759",
    "TOR": "1610612761",
    "UTA": "1610612762",
    "WAS": "1610612764",
}

LOGO_URLS = [
    "https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg",
    "https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.png",
    "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg",
    "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.png",
]

ASSETS_DIR = Path(__file__).parent / "scoresource" / "assets" / "logos" / "nba"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def download_logo(team_abbr, team_id):
    for url_template in LOGO_URLS:
        url = url_template.format(team_id=team_id)
        ext = ".svg" if url.endswith(".svg") else ".png"
        filename = f"{team_abbr}{ext}"
        dest = ASSETS_DIR / filename
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200 and resp.content:
                with open(dest, "wb") as f:
                    f.write(resp.content)
                print(f"Downloaded {team_abbr} logo to {dest}")
                return True
        except Exception as e:
            print(f"Failed to download {url}: {e}")
    print(f"No logo found for {team_abbr}")
    return False

def main():
    for abbr, team_id in NBA_TEAM_IDS.items():
        download_logo(abbr, team_id)

if __name__ == "__main__":
    main()

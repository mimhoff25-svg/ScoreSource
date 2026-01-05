"""Shared color palette for ScoreSource UI."""

# Primary palette
BG = "#0a0f1a"
PANEL = "#0f1726"
CARD = "#111c2d"
ACCENT = "#45e0ff"
ACCENT_SOFT = "#7cf3c8"
TEXT = "#eaf4ff"
TEXT_MUTED = "#6d88ab"

# Team panel gradients
TEAM_GRADIENT_TOP = "#1c2a3f"
TEAM_GRADIENT_BOTTOM = "#0b111d"

# NHL team colors and helpers (centralized to avoid duplication across modules)
TRICODE_ALIASES = {
	"LA": "LAK",
	"NJ": "NJD",
	"SJ": "SJS",
	"TB": "TBL",
	"WAS": "WSH",
}

TEAM_PRIMARY_COLORS = {
	"ANA": "#F47A38",
	"ARI": "#8C2633",
	"BOS": "#FFB81C",
	"BUF": "#002654",
	"CGY": "#C8102E",
	"CAR": "#CC0000",
	"CHI": "#CF0A2C",
	"COL": "#6F263D",
	"CBJ": "#002654",
	"DAL": "#006847",
	"DET": "#CE1126",
	"EDM": "#041E42",
	"FLA": "#041E42",
	"LAK": "#111111",
	"MIN": "#154734",
	"MTL": "#AF1E2D",
	"NSH": "#FFB81C",
	"NJD": "#C8102E",
	"NYI": "#00529B",
	"NYR": "#0038A8",
	"OTT": "#C52032",
	"PHI": "#F74902",
	"PIT": "#FCB514",
	"SEA": "#99D9D9",
	"SJS": "#006D75",
	"STL": "#002F87",
	"TBL": "#002868",
	"TOR": "#00205B",
	"VAN": "#00205B",
	"VGK": "#B4975A",
	"WSH": "#041E42",
	"WPG": "#041E42",
	# fallback demo codes
	"HME": "#4E4E4E",
	"AWY": "#2E2E2E",
}


def _scale(hex_color: str, factor: float) -> str:
	h = hex_color.lstrip("#")
	if len(h) != 6:
		return hex_color
	vals = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
	scaled = [min(255, max(0, int(v * factor))) for v in vals]
	return "#%02x%02x%02x" % tuple(scaled)


TEAM_SECONDARY_COLORS = {k: _scale(v, 0.65) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ACCENT_COLORS = {k: _scale(v, 1.3) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ALT_COLORS = dict(TEAM_ACCENT_COLORS)


def get_team_colors(tricode: str | None) -> dict:
	tri = (tricode or "").upper()
	tri = TRICODE_ALIASES.get(tri, tri)
	return {
		"primary": TEAM_PRIMARY_COLORS.get(tri, "#444444"),
		"secondary": TEAM_SECONDARY_COLORS.get(tri, "#2b2b2b"),
		"accent": TEAM_ACCENT_COLORS.get(tri, "#777777"),
		"alt": TEAM_ALT_COLORS.get(tri, "#777777"),
	}


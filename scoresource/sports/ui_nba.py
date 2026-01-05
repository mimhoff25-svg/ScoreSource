from scoresource.ui_base import BaseSportUI


class NBAScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("NBA", on_switch_sport, sport_options)

from scoresource.ui_base import BaseSportUI


class MLBScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("MLB", on_switch_sport, sport_options)

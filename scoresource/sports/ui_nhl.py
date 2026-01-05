from scoresource.ui_base import BaseSportUI


class NHLScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("NHL", on_switch_sport, sport_options)

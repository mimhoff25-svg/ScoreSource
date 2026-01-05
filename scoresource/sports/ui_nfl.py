from scoresource.ui_base import BaseSportUI


class NFLScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("NFL", on_switch_sport, sport_options)

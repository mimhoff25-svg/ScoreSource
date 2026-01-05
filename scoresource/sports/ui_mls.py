from scoresource.ui_base import BaseSportUI


class MLSScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("MLS", on_switch_sport, sport_options)

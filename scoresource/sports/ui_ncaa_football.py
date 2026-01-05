from scoresource.ui_base import BaseSportUI


class NCAAFootballScoreboardUI(BaseSportUI):
    def __init__(self, on_switch_sport, sport_options):
        super().__init__("NCAA Football", on_switch_sport, sport_options)

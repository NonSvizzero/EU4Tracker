import json
import os

from src import ASSETS_DIR


class Analyzer:
    start_date = "1444.11.12"

    def __init__(self, gameinfo):
        self.gameinfo = gameinfo
        self.player = gameinfo["meta"]["player"]
        self.countries = gameinfo["gamestate"]["countries"]

    @classmethod
    def from_file(cls, filename):
        with open(filename) as f:
            d = json.load(f)
            return cls(gameinfo=d)

    def get_player_history(self):
        for date, history in self.countries[self.player]["history"].items():
            print(date, history)


if __name__ == '__main__':
    analyzer = Analyzer.from_file(f"{ASSETS_DIR}/emperor.json")
    analyzer.get_player_history()

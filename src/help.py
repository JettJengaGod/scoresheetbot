class HelpDoc(dict):
    def __init__(self, brief: str, description='', usage=''):
        if not description:
            description = self.descriptify(brief)
        super().__init__(
            brief=brief,
            description=description,
            usage=usage
        )

    def descriptify(self, s):
        return s[0].upper() + s[1:] + '.'


help = dict(
    start=HelpDoc('Start a Scoresheet in this channel with two team names and a size',
                  'Takes 3 parameters, "Team1 Team2 Size"', "Team1 Team2 size"),
    add=HelpDoc('Add a player to a team', 'Takes 2 parameters, "TeamName PlayerName"', 'TeamName PlayerName'),
    end=HelpDoc('End the game with characters and stocks', 'Takes 4 parameters "Char1 Stocks1 Char2 Stocks2"',
                     'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc('Resize the crew battle',
                   'Takes 1 parameter: "NewSize" and resizes the crew battle to that size '
                   'unless too many games have already been played.',
                   'NewSize'),
    undo=HelpDoc('Undo the last match',
                 'Takes no parameters and undoes the last match that was played.'),
    echo=HelpDoc('Takes something and repeats it'),

)

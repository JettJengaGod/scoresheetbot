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
    battle=HelpDoc('Start a Scoresheet in this channel against the tagged players crew with a specific size',
                   '', "@OpponentName size"),
    send=HelpDoc('Sends in the tagged player', '', '@Player'),
    replace=HelpDoc('Replaces current player with the tagged player', '', '@Player'),
    end=HelpDoc('End the game with characters and stocks for both teams',
                'Example: `!end ness 3 palu 2` would say that the player on the first team played ness and took 3 stocks',
                'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc('Resize the crew battle',
                   'Takes 1 parameter: "NewSize" and resizes the crew battle to that size '
                   'unless too many games have already been played.',
                   'NewSize'),
    undo=HelpDoc('Undo the last match',
                 'Takes no parameters and undoes the last match that was played.'),
    crew=HelpDoc('Outputs what crew you are in.'),
    status=HelpDoc('Current status of the battle.'),
    chars=HelpDoc('Prints all characters names and their corresponding emojis'),
    clear=HelpDoc('Clears the current cb in the channel.'),
    confirm=HelpDoc('Confirms the final score sheet is correct.'),
    char=HelpDoc('Prints the character emoji (you can use this to test before entering in the sheet).'),
    arena=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    stream=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    timer=HelpDoc('Prints the time since the last match ended.'),
)

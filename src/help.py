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
    mock=HelpDoc('Start a Scoresheet in this channel with two team names and a size', '',
                 'Team1 Team2 size'),
    send=HelpDoc('Sends in the tagged player, if this is a mock you also need to send the team name', '',
                 '@Player Optional[TeamName]'),
    replace=HelpDoc('Replaces current player with the tagged player', '', '@Player Optional[TeamName]'),
    end=HelpDoc('End the game with characters and stocks for both teams',
                'Example: `!end ness 3 palu 2`, you can also choose alts here. use `,char CharName` to test it.',
                'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc('Resize the crew battle', '', 'NewSize'),
    undo=HelpDoc('Undo the last match',
                 'Takes no parameters and undoes the last match that was played.'),
    crew=HelpDoc('Outputs what crew a user is in or your crew if no user is sent.'),
    status=HelpDoc('Current status of the battle.'),
    chars=HelpDoc('Prints all characters names and their corresponding emojis'),
    clear=HelpDoc('Clears the current cb in the channel.'),
    confirm=HelpDoc('Confirms the final score sheet is correct.'),
    char=HelpDoc('Prints the character emoji (you can use this to test before entering in the sheet).',
                 'Put a number after the character name to use an alt, EG `,char ness2`.'
                 'CharName'),
    arena=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    stream=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    timer=HelpDoc('Prints the time since the last match ended'),
    guide=HelpDoc('Links to the guide'),
    recache=HelpDoc('Updates the cache. Admin only'),
    pending=HelpDoc('Prints pending battles. Admin only'),
    rank=HelpDoc('Find out a user\'s crew\'s rank'),
    merit=HelpDoc('Find out a user\'s crew\'s merit'),
    # unflair=HelpDoc('Unflairs you from your crew or a member from your crew if you are a leader '
    #                 'if you are an admin, unflairs anyone.', '', 'Optional<Member>'),
    # flair=HelpDoc('Flairs someone for your crew or for a specific crew if you are an admin. ', '',
    #               'Member Optional<Crew>'),
)

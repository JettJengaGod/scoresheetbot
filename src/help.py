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


help_doc = dict(
    battle=HelpDoc('Start a Scoresheet in this channel against the tagged players crew with a specific size',
                   '', "@OpponentName size"),
    mock=HelpDoc('Start a Scoresheet in this channel with two team names and a size', '',
                 'Team1 Team2 size'),
    send=HelpDoc('Sends in the tagged player, if this is a mock you also need to send the team name', '',
                 '@Player Optional[TeamName]'),
    replace=HelpDoc('Replaces current player with the tagged player', '', '@Player Optional[TeamName]'),
    end=HelpDoc('End the game with characters and stocks for both teams',
                'Example: `!end ness 3 palu 2`, you can also choose alts here. use `,char CharName` to test it',
                'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc('Resize the crew battle', '', 'NewSize'),
    undo=HelpDoc('Undo the last match',
                 'Takes no parameters and undoes the last match that was played'),
    timer_stock=HelpDoc('Lose a stock to the timer'),
    crew=HelpDoc('If provided with an argument, will search for a user\'s crew or '
                 'crew and output that, otherwise provides author\'s crew', '', 'Optional<User/Crew>'),
    status=HelpDoc('Current status of the battle'),
    chars=HelpDoc('Prints all characters names and their corresponding emojis'),
    clear=HelpDoc('Clears the current cb in the channel'),
    confirm=HelpDoc('Confirms the final score sheet is correct'),
    char=HelpDoc('Prints the character emoji (you can use this to test before entering in the sheet)',
                 'Put a number after the character name to use an alt, EG `,char ness2`'
                 'CharName'),
    arena=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    stream=HelpDoc('Sets the stream if you are a streamer or leader, or prints it if you are not'),
    timer=HelpDoc('Prints the time since the last match ended'),
    guide=HelpDoc('Links to the guide'),
    use_ext=HelpDoc('Uses your teams time extension in a crew battle'),
    ext=HelpDoc('Prints out extension status'),
    recache=HelpDoc('Updates the cache. Admin only'),
    pending=HelpDoc('Prints pending battles. Admin only'),
    rank=HelpDoc('Find out a user\'s crew\'s rank'),
    merit=HelpDoc('Find out a user\'s crew\'s merit'),
    unflair=HelpDoc('Unflairs you from your crew or a member from your crew if you are a leader '
                    'if you are an admin, unflairs anyone', '', 'Optional<Member>'),
    flair=HelpDoc('Flairs someone for your crew or for a specific crew if you are an admin', '',
                  'Member Optional<Crew>'),
    promote=HelpDoc('Used by leaders to promote users to advoisrs or staff to promote to leaders', '',
                    'User'),
    demote=HelpDoc('Used by leaders to demote advisors or staff to demote leaders', '',
                   'User'),
    overlap=HelpDoc('Find the overlap between two roles',
                    'Send in the two role names separated by spaces, it will try to find the best match',
                    'role1 role2'),
    cooldown=HelpDoc(
        'Finds the current cooldown for each of recently flaired users and fixes any that might have been missed'),
    non_crew=HelpDoc('Returns a list of all non crew roles (should be small)'),
    overflow=HelpDoc('Returns a two lists of overflow incorrectly tagged members'),
    flairing_off=HelpDoc('Turns flairing off until restart or staff turns it back on'),
    flairing_on=HelpDoc('Turns flairing back on'),
    disband=HelpDoc('Disbands an overflow crew removing all crew related roles from all members. (requires confirm)',
                    usage='CrewName or Tag'),
    retag=HelpDoc('Retags an overflow crew making all members have the proper tag. (requires confirm)',
                  usage='CrewName or Tag'),
    thank=HelpDoc('Thanks alexjett'),
)

class Categories:
    crews = 'crews'
    cb = 'cb'
    staff = 'staff'
    misc = 'misc'
    flairing = 'flairing'


class HelpDoc(dict):
    def __init__(self, help_txt, brief: str, description='', usage=''):
        if not description:
            description = self.descriptify(brief)
        super().__init__(
            help=help_txt,
            brief=brief,
            description=description,
            usage=usage
        )

    def descriptify(self, s):
        return s[0].upper() + s[1:] + '.'


help_doc = dict(
    battle=HelpDoc(Categories.cb,
                   'Start a Scoresheet in this channel against the tagged players crew with a specific size',
                   '', "@OpponentName size"),
    mock=HelpDoc(Categories.cb, 'Start a Scoresheet in this channel with two team names and a size', '',
                 'Team1 Team2 size'),
    send=HelpDoc(Categories.cb, 'Sends in the tagged player, if this is a mock you also need to send the team name', '',
                 '@Player Optional[TeamName]'),
    replace=HelpDoc(Categories.cb, 'Replaces current player with the tagged player', '', '@Player Optional[TeamName]'),
    end=HelpDoc(Categories.cb, 'End the game with characters and stocks for both teams',
                'Example: `!end ness 3 palu 2`, you can also choose alts here. use `,char CharName` to test it',
                'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc(Categories.cb, 'Resize the crew battle', '', 'NewSize'),
    undo=HelpDoc(Categories.cb, 'Undo the last match',
                 'Takes no parameters and undoes the last match that was played'),
    timer_stock=HelpDoc(Categories.cb, 'Lose a stock to the timer'),
    crew=HelpDoc(Categories.crews, 'If provided with an argument, will search for a user\'s crew or '
                                   'crew and output that, otherwise provides author\'s crew', '',
                 'Optional<User/Crew>'),
    status=HelpDoc(Categories.cb, 'Current status of the battle'),
    chars=HelpDoc(Categories.cb, 'Prints all characters names and their corresponding emojis'),
    clear=HelpDoc(Categories.cb, 'Clears the current cb in the channel'),
    confirm=HelpDoc(Categories.cb, 'Confirms the final score sheet is correct'),
    char=HelpDoc(Categories.cb, 'Prints the character emoji (you can use this to test before entering in the sheet)',
                 'Put a number after the character name to use an alt, EG `,char ness2`'
                 'CharName'),
    arena=HelpDoc(Categories.cb, 'Sets the stream if you are a streamer or leader, or prints it if you are not'),
    stream=HelpDoc(Categories.cb, 'Sets the stream if you are a streamer or leader, or prints it if you are not'),
    timer=HelpDoc(Categories.cb, 'Prints the time since the last match ended'),
    guide=HelpDoc(Categories.misc, 'Links to the guide'),
    use_ext=HelpDoc(Categories.cb, 'Uses your teams time extension in a crew battle'),
    ext=HelpDoc(Categories.cb, 'Prints out extension status'),
    recache=HelpDoc(Categories.staff, 'Updates the cache. Admin only'),
    pending=HelpDoc(Categories.staff, 'Prints pending battles. Admin only'),
    rank=HelpDoc(Categories.crews, 'Find out a user\'s crew\'s rank'),
    merit=HelpDoc(Categories.crews, 'Find out a user\'s crew\'s merit'),
    unflair=HelpDoc(Categories.flairing, 'Unflairs you from your crew or a member from your crew if you are a leader '
                                         'if you are an admin, unflairs anyone', '', 'Optional<Member>'),
    flair=HelpDoc(Categories.flairing, 'Flairs someone for your crew or for a specific crew if you are an admin', '',
                  'Member Optional<Crew>'),
    promote=HelpDoc(Categories.flairing, 'Used by leaders to promote users to advoisrs or staff to promote to leaders',
                    '',
                    'User'),
    demote=HelpDoc(Categories.flairing, 'Used by leaders to demote advisors or staff to demote leaders', '',
                   'User'),
    overlap=HelpDoc(Categories.misc, 'Find the overlap between two roles',
                    'Send in the two role names separated by spaces, it will try to find the best match',
                    'role1 role2'),
    cooldown=HelpDoc(Categories.staff,
                     'Finds the current cooldown for each of recently flaired users and fixes any that might have been missed'),
    non_crew=HelpDoc(Categories.staff, 'Returns a list of all non crew roles (should be small)'),
    overflow=HelpDoc(Categories.staff, 'Returns a two lists of overflow incorrectly tagged members'),
    flairing_off=HelpDoc(Categories.staff, 'Turns flairing off until restart or staff turns it back on'),
    flairing_on=HelpDoc(Categories.staff, 'Turns flairing back on'),
    disband=HelpDoc(Categories.staff,
                    'Disbands an overflow crew removing all crew related roles from all members. (requires confirm)',
                    usage='CrewName or Tag'),
    retag=HelpDoc(Categories.staff,
                  'Retags an overflow crew making all members have the proper tag. (requires confirm)',
                  usage='CrewName or Tag'),
    thank=HelpDoc(Categories.misc, 'Thanks alexjett'),
)

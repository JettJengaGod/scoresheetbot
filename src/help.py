class Categories:
    crews = 'crews'
    cb = 'cb'
    staff = 'staff'
    misc = 'misc'
    flairing = 'flairing'
    gambit = 'gambit'
    ba = 'ba'


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
    masterbattle=HelpDoc(Categories.cb,
                         'Start a master league Scoresheet in this channel against'
                         ' the tagged players\' crew with a specific size',
                         '', "@OpponentName size"),
    bfplayoff=HelpDoc(Categories.cb,
                      'Start a battle frontier playoff Scoresheet in this channel against'
                      ' the tagged players\' crew with a specific size',
                      '', "@OpponentName size"),
    rcplayoff=HelpDoc(Categories.cb,
                      'Start a rookie class playoff Scoresheet in this channel against'
                      ' the tagged players\' crew with a specific size',
                      '', "@OpponentName size"),
    playoffbattle=HelpDoc(Categories.cb,
                          'Start a master league playoff Scoresheet in this channel against'
                          ' the tagged players\' crew with a specific size',
                          '', "@OpponentName size"),
    mock=HelpDoc(Categories.cb, 'Start a Mock Scoresheet in this channel with two team names and a size', '',
                 'Team1 Team2 size'),
    reg=HelpDoc(Categories.cb, 'Start a Registration Scoresheet in this channel with two team names and a size', '',
                'RegisteringCrewName size'),
    send=HelpDoc(Categories.cb, 'Sends in the tagged player, if this is a mock you also need to send the team name', '',
                 '@Player Optional[TeamName]'),
    replace=HelpDoc(Categories.cb, 'Replaces current player with the tagged player', '', '@Player Optional[TeamName]'),
    end=HelpDoc(Categories.cb, 'End the game with characters and stocks for both teams',
                'Example: `!end ness 3 palu 2`, you can also choose alts here. use `,char CharName` to test it',
                'Char1 StocksTaken1 Char2 StocksTaken2'),
    endlag=HelpDoc(Categories.cb,
                   'End the game with characters and stocks for both teams. '
                   'Same as end, but does not need to result in one player winning'
                   'Example: `!end ness 3 palu 2`, you can also choose alts here. use `,char CharName` to test it',
                   'Char1 StocksTaken1 Char2 StocksTaken2'),
    resize=HelpDoc(Categories.cb, 'Resize the crew battle', '', 'NewSize'),
    undo=HelpDoc(Categories.cb, 'Undo the last match',
                 'Takes no parameters and undoes the last match that was played'),
    timerstock=HelpDoc(Categories.cb, 'Your current player will lose a stock to the timer'),
    lock=HelpDoc(Categories.cb, 'Locks the cb room to only crews playing in it'),
    unlock=HelpDoc(Categories.cb, 'Unlocks cb room to everyone'),
    forfeit=HelpDoc(Categories.cb, 'Forfeits a crew battle'),
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
    coin=HelpDoc(Categories.misc, 'Flips a coin. If you mention a user it will '
                                  'prompt them to answer heads or tails before the flip.'),
    use_ext=HelpDoc(Categories.cb, 'Uses your teams time extension in a crew battle'),
    difficulty=HelpDoc(Categories.cb, 'Sets the difficulty for an arcade match'),
    ext=HelpDoc(Categories.cb, 'Prints out extension status'),
    recache=HelpDoc(Categories.staff, 'Updates the cache. Admin only'),
    pending=HelpDoc(Categories.staff, 'Prints pending battles. Admin only'),
    po=HelpDoc(Categories.staff, 'Prints all final stand cbs in a summary'),
    disable=HelpDoc(Categories.staff, 'Disables the bot in a channel', '', 'ChannelMention'),
    usage=HelpDoc(Categories.staff, 'Shows the usage stats of each command'),

    deactivate=HelpDoc(Categories.staff, 'Deactivates a command so the bot will not '
                                         'be able to use it till reactivation, also reactivates commands', '',
                       'CommandName'),
    countdown=HelpDoc(Categories.cb, 'Counts down for x seconds (defaults to 3).'),
    slots=HelpDoc(Categories.crews, 'Find out the remaining slots of a crew'),
    logo=HelpDoc(Categories.crews, 'Find the logo of a crew'),
    rankings=HelpDoc(Categories.crews, 'Rankings of all legacy crews in order'),
    crewstats=HelpDoc(Categories.crews, 'Stats for a crew or the crew of a player'),
    umbralotto=HelpDoc(Categories.crews, 'Random Crew of a Certian Rank'),
    history=HelpDoc(Categories.crews, 'Crew history of a member'),
    vod=HelpDoc(Categories.crews, 'Used for a streamer or admin to set the vod of a match', '', 'battle_id vod_url'),
    playerstats=HelpDoc(Categories.crews, 'Stats for a player'),
    stats=HelpDoc(Categories.crews, 'Stats for a player or crew, depending on what you send in'),
    battles=HelpDoc(Categories.crews, 'All battles that have been recorded with the bot'),
    unflair=HelpDoc(Categories.flairing, 'Unflairs you from your crew or a member from your crew if you are a leader '
                                         'if you are an admin, unflairs anyone', '', 'Optional<Member>'),
    multiflair=HelpDoc(Categories.flairing,
                       'Flairs multiple people for your crew or for a specific crew if you are an admin.'
                       'Only use spaces between members, and mention mention each one', '',
                       'Member1 Member2 Member3 Optional<Crew>'),
    multiunflair=HelpDoc(Categories.flairing,
                         'Unflairs multiple people for your crew or for a specific crew if you are an admin.'
                         'Only use spaces between members, and mention mention each one', '',
                         'Member1 Member2 Member3'),
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
    noverlap=HelpDoc(Categories.misc, 'Find members that have one role but not another',
                     'Send in the two role names separated by spaces, it will try to find the best match',
                     'role1 role2'),
    listroles=HelpDoc(Categories.misc, 'Find the users with this role', '', 'role'),
    roster=HelpDoc(Categories.misc, 'Find the members of the crews roster, defaults to author crew', '', 'role'),
    disablelist=HelpDoc(Categories.misc, 'List of channels disabled for jettbot'),

    pingrole=HelpDoc(Categories.staff, 'Same As listroles, but pings instead', '', 'role'),
    setslots=HelpDoc(Categories.staff, 'Sets the slots for a crew to a specific number', '', 'number Crew'),
    setreturnslots=HelpDoc(Categories.staff,
                           'Sets the return slots for a crew to a specific number (Only values 1,2,3)', '',
                           'number Crew'),
    cooldown=HelpDoc(Categories.staff,
                     'Finds the current cooldown for each of recently flaired users and fixes any that might have been missed'),
    non_crew=HelpDoc(Categories.staff, 'Returns a list of all non crew roles (should be small)'),
    overflow=HelpDoc(Categories.staff, 'Returns a two lists of overflow incorrectly tagged members'),
    ofrank=HelpDoc(Categories.staff, 'Returns all overflow crews and info about them'),
    flairing_off=HelpDoc(Categories.staff, 'Turns flairing off until restart or staff turns it back on'),
    flairing_on=HelpDoc(Categories.staff, 'Turns flairing back on'),
    pair=HelpDoc(Categories.staff, 'Pairs 2 crews for destiny', 'Crew1 Crew2'),
    freeze=HelpDoc(Categories.staff, 'Freezes a crews registration for a time.',
                   'If you pass in a time it will stop a crew from registering for that amount of time,'
                   ' accepts xD or xW or xM for x days, weeks or months respectively', 'CREW Optional[length]'),
    disband=HelpDoc(Categories.staff,
                    'Disbands an overflow crew removing all crew related roles from all members. (requires confirm)',
                    usage='CrewName or Tag'),
    tomain=HelpDoc(Categories.staff,
                   'Move an overflow crew to main. (requires confirm)',
                   usage='CrewName or Tag'),
    charge=HelpDoc(Categories.staff,
                   'Charges a user an amount of gcoins for a reason',
                   usage='@member amount reason'),
    retag=HelpDoc(Categories.staff,
                  'Retags an overflow crew making all members have the proper tag. (requires confirm)',
                  usage='CrewName or Tag'),
    thank=HelpDoc(Categories.misc, 'Thanks alexjett'),
    thankboard=HelpDoc(Categories.misc, 'Returns the thanking leaderboard'),
    stagelist=HelpDoc(Categories.misc, 'Returns the stagelist'),
    invite=HelpDoc(Categories.misc, 'Returns the server invite'),
    records=HelpDoc(Categories.misc, 'Returns the docs'),
    make_lead=HelpDoc(Categories.staff, 'Makes a user a leader on their crew', '', 'User'),
    bigcrew=HelpDoc(Categories.staff, 'Returns all the crews that are bigger than x, default 40', '', 'Crew min'),
    softcap=HelpDoc(Categories.crews,
                    'Returns the number of unique players used by crews last month or the players and each cb'
                    'for a specific crew', '', 'Optional[Crew]'),
    crnumbers=HelpDoc(Categories.staff, 'Helpful numbers for crew analysis'),
    cancelcb=HelpDoc(Categories.staff, 'Cancel a crew battle that happened in the past', '',
                     'battleId Optional[Reason]'),
    slottotals=HelpDoc(Categories.staff, 'Prints all the max slots for crews'),
    flaircounts=HelpDoc(Categories.staff, 'Helpful numbers for flair analysis'),
    opt=HelpDoc(Categories.staff, 'Opts a crew out of destiny or back in'),
    addsheet=HelpDoc(Categories.staff, 'Adds a new non bot sheet to the database and in scoresheet_history', '',
                     'Winner Loser Size FinalScore'),
    addforfeit=HelpDoc(Categories.staff, 'Adds a forfeit sheet to the database and in scoresheet_history', '',
                     'Winner Loser'),
    failedreg=HelpDoc(Categories.staff, 'Adds a new reg cb sheet to the database and in scoresheet_history', '',
                      'Winner Loser Size FinalScore'),
    weirdreg=HelpDoc(Categories.staff, 'Adds a new reg cb sheet where the registering crew won but didn\'t reg'
                                       'to the database and in scoresheet_history', '',
                     'LosingCrew WinningRegCrew Size FinalScore'),
    pingoverlap=HelpDoc(Categories.staff, 'Pings the overlap between two roles', '', 'role 1 role 2'),
    pingnoverlap=HelpDoc(Categories.staff, 'Pings all members with the first role but not the 2nd', '',
                         'role 1 role 2'),
    register=HelpDoc(Categories.staff,
                     'Flairs multiple people for a new crew'
                     'Only use spaces between members, and mention mention each one', '',
                     'Member1 Member2 Member3 Crew'),
    fixslot=HelpDoc(Categories.staff,
                    'Adds a slot to a crew that for some reason didnt have it'),
    coins=HelpDoc(Categories.gambit, 'Shows your gcoins'),
    bet=HelpDoc(Categories.gambit, 'Bets an amount on a crew, only valid while a gambit is active.', '', 'amount crew'),
    odds=HelpDoc(Categories.gambit, 'Tells you the current odds for the gambit'),
    predictions=HelpDoc(Categories.gambit, 'Tells you your predictions for the MC playoffs'),
    predict=HelpDoc(Categories.gambit, 'Lets you predict the MC playoffs'),
    result=HelpDoc(Categories.ba, 'Submits a battle arena result'),
    vote=HelpDoc(Categories.misc, 'Vote for an option between 1 and 4')
)

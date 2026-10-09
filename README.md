# Score Sheet Bot

## Development

### Python Setup

1. Optional: Create `venv`, and activate via `venv/Scripts/activate`.
1. Install dependencies with `pipenv install`
    * You may need to install Visual Studio Build Tools from [here](https://visualstudio.microsoft.com/downloads/) for some dependencies.

### Google Credentials Setup

1. Go to https://developers.google.com/sheets/api/quickstart/python and enable the Google Sheets API.
1. Move `credentials.json` to the project folder.
   * This will be used on the first command run that needs access to the spreadsheet. You may grant access from the url redirect, and verify the app you created via the 'advanced' option on the bottom left.
1. Also download the client key from this section and rename it `client_key.json`
### Discord Bot Setup

1. Create an application at https://discord.com/developers/applications.
1. Under the app, create a Bot.
1. Under Bot/Privileged Gateway Intents, nothing needs enabling for now. The server members intent is switched off until it's approved; to switch it back on, enable it here and set `MEMBERS_INTENT=1` in `.env`, and the bot goes back to using the member list everywhere. Until then, `src/no_members_intent.py` stands in for the member list: crew member counts, leaders and member lists come from the database, and members are fetched from Discord when a command needs them. The member join and leave events still don't arrive, and commands that list everyone with a role (`listroles`, `overlap`, `noverlap`, the staff ping commands) only see members the bot has fetched since it started. The bot never needs the presence or message content intents.
1. Copy `.envexample` to `.env`, and add the token from the Bot page.
1. Invite your bot to your test server via `https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=519232&scope=bot%20applications.commands`, where the client id is found in your General Information page.
   * The `applications.commands` scope is what lets the bot's slash commands show up. A bot invited without it can be re-authorised with the same link.
1. Optional: set `SYNC_GUILD_ID` in `.env` to your test server's id. Slash commands are then registered on that server when the bot starts and appear straight away; without it they are registered globally, which can take a while to show up.

### Datbase Setup
1. Setup your `database.ini` file based on the example provided.


### Slash commands

Every command is a slash command (`/cb send`); the bot has no prefix commands and doesn't read messages for them.
Slash commands are sorted into sections: `/cb` (crew battles), `/f` (flairing), `/crew`, `/gambit`, `/roles`, `/misc` and `/staff`, for example `/crew stats` or `/staff battle addsheet`. `/help` is on its own, and lists these sections; `/help cb` lists the commands in one.
Slash commands are registered when the bot starts, so restart the bot after adding or changing a command.

### Tests

Run `python -m pytest tests`. `tests/data` holds recorded snapshots of command output; after an intended change, re-record them with `UPDATE_SNAPSHOTS=1 python -m pytest tests` and review the diff.

### Run Bot

You may run the bot via `pipenv run start`, or `python src/main.py`.
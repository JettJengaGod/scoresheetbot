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

### Discord Bot Setup

1. Create an application at https://discord.com/developers/applications.
1. Under the app, create a Bot.
1. Under Bot/Privileged Gateway Intents, enable both presence intent and server members intent.
1. Copy `.envexample` to `.env`, and add the token from the Bot page.
1. Invite your bot to your test server via `https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=519232&scope=bot`, where the client id is found in your General Information page.

### Run Bot

You may run the bot via `pipenv run start`, or `python src/main.py`.
# Deploy NixicRobot on Render

This bot is configured as a Render Web Service because `python -m AloneX` starts an `aiohttp` server before starting Telegram polling.

## Render settings

- Runtime: Python
- Build command: `pip install --upgrade pip setuptools wheel && pip install -r requirements.txt`
- Start command: `python -m AloneX`
- Health check path: `/`
- Python version: `3.12` from `.python-version`

If you deploy with the Blueprint, commit `render.yaml` to your GitHub/GitLab/Bitbucket repo and create a new Blueprint in Render.

## Required environment variables

Set these in Render before the first deploy:

```env
TOKEN=your_telegram_bot_token
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
DB_URL=your_mongodb_connection_string
DB_URL2=your_second_mongodb_connection_string
USER_STRING=your_pyrogram_user_session_string
OWNER_ID=your_telegram_user_id
ALONE_OWNER_ID=your_telegram_user_id
SUDO_USERS=your_telegram_user_id
SUPPORT_USERS=your_telegram_user_id
WHITELIST_USERS=your_telegram_user_id
DEV_LIST=your_telegram_user_id
BOT_USERNAME=@Sayafaqbot
BOT_NAME=Nixie
IS_WEB_SUP=True
WEB_SERVER_BIND_ADDRESS=0.0.0.0
WEB_URL=https://sayafaqbot.onrender.com/
```

`WEB_URL` should be your final Render URL. If the generated Render URL is different from the service name, update `WEB_URL` after Render creates the service and redeploy.

## Optional feature variables

```env
LOGS_CHANNEL=
LOGGER_ID=
LOG_GROUP_ID=
GROQ_API_KEY=
GEMINI_API_KEY=
MONSTER_API_KEY=
REPLICATE_API_TOKEN=
ELEVENLABS_API_KEY=
IMAGE_UPLOAD_KEY=
GIST_TOKEN=
TELEGRAPH_TOKEN=
FALLEN_API_KEY=
PINTEREST_COOKIE=
ZZZCODE_COOKIE=
FILE_DB_CHANNEL=0
AF_SUB_CHAT=@AloneUpdates
```

Do not commit a real `.env` file. Use `.env.example` or `sample.env` only as templates.

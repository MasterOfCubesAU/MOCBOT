![github_banner_slim](https://github.com/MasterOfCubesAU/MOCBOT/assets/38149391/9f5f850c-cead-4e5e-9cab-ecdf886b6b9a)

[![GPLv3 License](https://img.shields.io/badge/License-GPL%20v3-yellow.svg)](https://opensource.org/licenses/)

# MOCBOT: The Discord Bot

MOCBOT is a discord bot made to solve all your automation needs. MOCBOT allows for automated Discord server management.

Manage MOCBOT configuration through the [MOCBOT Website](https://mocbot.masterofcubesau.com/).

## Authors

- [@MasterOfCubesAU](https://www.github.com/MasterOfCubesAU)
- [@samiam](https://github.com/sam1357)

## Features

- **User XP/Levels** (Voice and Text XP dsitribution, Server Leaderboards, Role Rewards, XP Management)
- **Private Lobbies** (Create your own private lobby and allow specific people to access it)
- **Music** (Play any media from sources like YouTube, Spotify, SoundCloud and Apple Music)
- Music Filters (Spice up your music with some cool effects)
- User Management (Kicks/Bans/Warnings)
- Customisable Announcement Messages
- Channel Purging
- Bot Logging (To be ported)
- User Verification (To be ported)
- Support Tickets (To be ported)

## Usage

Invite MOCBOT into your Discord server [here](https://discord.com/api/oauth2/authorize?client_id=417962459811414027&permissions=8&scope=bot%20applications.commands).

Type `/` in your Discord server to see available commands. Alternatively, you may view all commands [here](https://mocbot.masterofcubesau.com/commands)

## Deployment

MOCBOT is intended to be deployed as a whole system. See [MOCBOT Sytem](https://github.com/MasterOfCubesAU/mocbot-system).

If you still wish to proceed and deploy MOCBOT's bot instance individually, ensure you have installed the following:

- [Docker Desktop](https://docs.docker.com/desktop/) or [Docker Engine](https://docs.docker.com/engine/)

### Setup

You will now need to populate a `config.yml` file in order for MOCBOT to run. See [config.template.yml](./config.template.yml) for a template.

Once the above setup is complete, run:

```bash
docker build . -t mocbot-bot
docker run mocbot-bot
```

## Feedback

If you have any feedback, please reach out to us at https://masterofcubesau.com/contact

## License

[GPL v3](https://choosealicense.com/licenses/gpl-3.0/)

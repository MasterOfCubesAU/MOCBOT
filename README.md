
![](https://mocbot.masterofcubesau.com/static/media/github_banner_slim.png)

[![GPLv3 License](https://img.shields.io/badge/License-GPL%20v3-yellow.svg)](https://opensource.org/licenses/)

# MOCBOT: The Discord Bot

MOCBOT is a discord bot made to solve all your automation needs. MOCBOT allows for automated Discord server management.

Manage MOCBOT configuration through the [MOCBOT Website](https://mocbot.masterofcubesau.com/).



## Authors

- [@MasterOfCubesAU](https://www.github.com/MasterOfCubesAU)


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

MOCBOT currently isn't intended to be deployed, however, the capability to deploy MOCBOT does exist.

To deploy MOCBOT, ensure you have installed the following:

- [Python 3.10](https://www.python.org/downloads/release/python-3108/)

To deploy this project run

```bash
  python3.10 install.py
  
  # Windows
  .MOCBOT\Scripts\python launcher.py
  # Unix
  .MOCBOT/bin/python launcher.py
```

You will now need to populate a `config.yml` file in order for MOCBOT to run. See [config.template.yml](https://github.com/MasterOfCubesAU/MOCBOT/blob/master/config.template.yml) for a template.


## Branches

- [master](https://github.com/MasterOfCubesAU/MOCBOT/tree/master) - The main public release of MOCBOT
- [dev](https://github.com/MasterOfCubesAU/MOCBOT/branches/all?query=dev) - The development releases of MOCBOT. All functionality of this branch is experimental and may have bugs.
## Feedback

If you have any feedback, please reach out to us at https://masterofcubesau.com/contact


## License

[GPL v3](https://choosealicense.com/licenses/gpl-3.0/)


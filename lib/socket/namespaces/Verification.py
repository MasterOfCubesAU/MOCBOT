import asyncio
from hashlib import sha256
import logging
import sys
import socketio
from socketio.exceptions import ConnectionRefusedError
import yaml

with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)

class Verification(socketio.AsyncNamespace):
    async def on_connect(self, socketID, environ):
        socketKey = environ.get("HTTP_SOCKET_KEY")
        if socketKey is None or (socketKey is not None and sha256(socketKey.encode('utf-8')).hexdigest() != config["SOCKET_KEY"]):
            logging.getLogger(__name__).warning(f"Unauthorised connection from {environ.get('REMOTE_ADDR', None)}")
            raise ConnectionRefusedError("Unauthorised")

    async def on_disconnect(self, socketID):
        pass

    async def on_verify_user(self, socketID, data):
        async def waitForVerification():
            while('lib.cogs.Verification' not in sys.modules):
                await asyncio.sleep(1)
            from lib.cogs.Verification import Verification as VerificationCog
            await VerificationCog.web_verify_user(data.get("UserID"), data.get("GuildID"), captcha=data.get("Captcha"), adminID=data.get("AdminID"))
        asyncio.ensure_future(waitForVerification())
    
    async def on_verify_kick_user(self, socketID, data):
        async def waitForVerification():
            while('lib.cogs.Verification' not in sys.modules):
                await asyncio.sleep(1)
            from lib.cogs.Verification import Verification as VerificationCog
            await VerificationCog.web_kick_user(data.get("UserID"), data.get("GuildID"), data.get("AdminID"))
        asyncio.ensure_future(waitForVerification())
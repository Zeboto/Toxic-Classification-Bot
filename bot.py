# -*- coding: utf-8 -*-

import asyncio
import hashlib
import logging
import traceback
from pathlib import Path

import aiohttp

import discord
from discord.ext import commands



class FlagBot(commands.Bot):
    def __init__(self, *args, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.config = config or {}
        
        #: OAuth2 application owner.
        self.owner: discord.User = None

        #: List of extension names to load. We store this because `self.extensions` is volatile during reload.
        self.to_load: typing.List[str] = None
        
        self.logger = logging.getLogger('flagbot')

        self.remove_command('help')

        self.session = aiohttp.ClientSession(loop=self.loop)
    async def on_ready(self):
        self.discover_exts('cogs')
        self.logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    async def on_command_error(self, ctx: commands.Context, exception):
        msg = ctx.message
        if isinstance(exception, (commands.CommandOnCooldown, commands.CommandNotFound,
                                  commands.DisabledCommand, commands.MissingPermissions,
                                  commands.CheckFailure)):
            pass  # we don't care about these
        elif isinstance(exception, (commands.BadArgument, commands.MissingRequiredArgument)):
            try:
                await msg.add_reaction("\N{BLACK QUESTION MARK ORNAMENT}")
            except discord.HTTPException:
                pass
        else:
            error_digest = "".join(traceback.format_exception(type(exception), exception,
                                                              exception.__traceback__, 8))
            error_hash = hashlib.sha256(error_digest.encode("utf8")).hexdigest()
            short_hash = error_hash[0:8]
            self.logger.error(f"Encountered command error [{error_hash}] ({msg.id}):\n{error_digest}")
            await ctx.send(f"Uh-oh, that's an error [{short_hash}...]")

    async def is_owner(self, user):
        if user.id in self.config.get("admin_users", []):
            return True
        return await super().is_owner(user)
    
    
    def discover_exts(self, directory: str):
        """Loads all extensions from a directory."""
        ignore = {'__pycache__', '__init__'}

        exts = [
            p.stem for p in Path(directory).resolve().iterdir()
            if p.stem not in ignore
        ]

        self.logger.info('Loading extensions: %s', exts)

        for ext in exts:
            self.load_extension('cogs.' + ext)

        self.to_load = list(self.extensions.keys()).copy()
        self.logger.info('To load: %s', self.to_load)
# -*- coding: utf-8 -*-
import aioredis
import asyncio
import asyncpg
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
        self.redis = None
        self.config = config or {}
        self.db = None
        self.db_available = asyncio.Event()

        #: OAuth2 application owner.
        self.owner: discord.User = None

        #: List of extension names to load. We store this because `self.extensions` is volatile during reload.
        self.to_load: typing.List[str] = None
        
        self.logger = logging.getLogger('flagbot')

        self.remove_command('help')

        self.session = aiohttp.ClientSession(loop=self.loop)
        self.loop.create_task(self.acquire_pool())

    async def acquire_pool(self):
        credentials = self.config.pop("database")

        if not credentials:
            self.logger.critical("Cannot connect to db, no credentials!")
            await self.logout()
        
        self.db = await asyncpg.create_pool(**credentials)
        self.db_available.set()

    async def on_ready(self):
        self.redis = await aioredis.create_redis_pool(**self.config['redis'])
        self.discover_exts('cogs')
        self.logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    async def load_cache(self):
        conn = self.get_db()

        self.config['reviewer_channels'] = await conn.load_reviewer_channels()
        self.config['scan_channels'] = await conn.load_scan_channels()
        for c in self.config['reviewer_channels']:
            channel = self.get_channel(c['channel_id']) or await self.fetch_channel(c['channel_id'])
            if len(await channel.webhooks()) == 0:
                await channel.create_webhook(name='FlagBot')
            
        channel = self.get_channel(self.config['stats_channel']) or await self.fetch_channel(self.config['stats_channel'])
        if len(await channel.webhooks()) == 0:
            await channel.create_webhook(name='FlagBot')

        channel = self.get_channel(self.config['sanitize_channel']) or await self.fetch_channel(self.config['sanitize_channel'])
        if len(await channel.webhooks()) == 0:
            await channel.create_webhook(name='FlagBot')

    def get_db(self):
        conn = self.get_cog('DBUtils')
        if conn is None:
            self.bot.logger.info("The cog \"DBUtils\" is not loaded")
            return
        return conn
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
            '.'.join(list(p.parts)).replace('.py','') for p in list(Path(directory).glob('**/*.py'))
            if p.stem not in ignore
        ]

        self.logger.info('Loading extensions: %s', exts)

        for ext in exts:
            self.load_extension(ext)

        self.to_load = list(self.extensions.keys()).copy()
        self.logger.info('To load: %s', self.to_load)
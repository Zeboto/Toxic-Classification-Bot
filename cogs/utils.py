# -*- coding: utf-8 -*-
import asyncio
import toml
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from utils.checks import check_granted_server
from asyncpg.exceptions import UniqueViolationError


class Rollback(Exception):
    pass


class Utils(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.messages = []
        self.message_lock = asyncio.Lock()
        self.compute_lock = asyncio.Lock()
            

    @commands.check(check_granted_server)
    @commands.command("add_channel")
    async def add_channel_command(self, ctx: commands.Context, channel_id: int=0):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Channel not found!")
            return
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.fetch(
                        """
                        INSERT INTO scan_channels (channel_id, server_id)
                            VALUES ($1, $2)
                        """,
                        channel.id,
                        channel.guild.id
                    )
                    await ctx.send(f"Channel `{channel.name}` from **{channel.guild.name}** added to scan list.")
                except UniqueViolationError:
                    await ctx.send(f"{ctx.author.mention} Sorry, that channel already exists.")
                    pass
        
        
    
    @commands.is_owner()
    @commands.command("reload_config")
    async def reload_channel_command(self, ctx: commands.Context):
        with open('config.toml', 'r', encoding='utf-8') as f:
            data = toml.load(f)
        self.bot.config = data
        await ctx.send(f"Reloaded config.")
    
    @commands.is_owner()
    @commands.command("update_config")
    async def update_config_command(self, ctx: commands.Context):
        with open('config.toml', 'w') as f:
            toml.dump(self.bot.config, f)
        await ctx.send(f"Updated config.")
        
    @commands.check(check_granted_server)
    @commands.command("blacklist", aliases=['bl'])
    async def blacklist_command(self, ctx: commands.Context, *, phrase: str=''):
        with open('config.toml', 'r', encoding='utf-8') as f:
            data = toml.load(f)
        if len(phrase) <= 1:
            await ctx.send(f"That phrase is too short!")
            return
        data['blacklist'].append(phrase)
        self.bot.config = data
        with open('config.toml', 'w') as f:
            toml.dump(data, f)
        await ctx.send(f"Added `{phrase}` to the blacklist.")
def setup(bot):
    bot.add_cog(Utils(bot))


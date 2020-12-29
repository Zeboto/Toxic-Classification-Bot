# -*- coding: utf-8 -*-
import asyncio
import toml
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from utils.checks import check_granted_server



class Rollback(Exception):
    pass


class DBChecks(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
            

    async def in_scan_channel(self, channel_id: int):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(
                """
                SELECT COUNT(*) FROM scan_channels WHERE channel_id = $1 
                """,
                channel_id
            )
            return record['count'] != 0
            
def setup(bot):
    bot.add_cog(DBChecks(bot))


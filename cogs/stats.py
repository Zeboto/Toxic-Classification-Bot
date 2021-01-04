import asyncio
import logging
import os
import random
import re
import json
from datetime import datetime, timedelta

from typing import TYPE_CHECKING
from utils.decorators import timing

if TYPE_CHECKING:
    from bot import FlagBot


import discord
import pandas as pd
from discord.ext import commands
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

log = logging.getLogger(__name__)


class Stats(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: "FlagBot" = bot
        self.stat_message = None
        self.completed = 0
        self.remaining = 0
        self.reviewer_stats = {}
        self.last_stats = None
        asyncio.create_task(self.clean_channel())
        asyncio.create_task(self.create_stats())

    async def clean_channel(self):
        await self.bot.wait_until_ready()
        # Clear review queue
        channel = self.bot.get_channel(self.bot.config.get('stats_channel'))
        await channel.purge(limit=100)

    @timing(log=log)
    async def create_stats(self):
        await self.bot.load_cache()
        
        reviewers = [x['user_id'] for x in self.bot.config['reviewer_channels']]
        channel = self.bot.get_channel(self.bot.config.get('stats_channel'))
        webhook = (await channel.webhooks())[0]
        if not self.stat_message:
            message = await webhook.send(content="Stats", wait=True)
            self.stat_message = message.id
        data = {'method': 'update_stats', 'channel': self.bot.config.get('stats_channel'), 'message': self.stat_message, 'reviewers': reviewers, 'url': webhook.url}
        await self.bot.redis.rpush('flagbot:queue', json.dumps(data))
    
def setup(bot):
    bot.add_cog(Stats(bot))

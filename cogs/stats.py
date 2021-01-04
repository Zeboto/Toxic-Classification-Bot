import asyncio
import logging

from datetime import datetime

from utils.classes import Cog

from utils.decorators import timing

import discord

log = logging.getLogger(__name__)

class Stats(Cog):
    stat_message: int = None
    completed: int = 0
    remaining: int = 0
    reviewer_stats = {}
    last_stats = None

    def __init__(self, bot) -> None:
        super().__init__(bot)

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

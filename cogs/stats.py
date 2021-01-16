import asyncio
import logging
import os
import random
import re
import json
from datetime import datetime, timedelta
from utils.checks import check_granted_server

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
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore reactions from the bot
        if (payload.user_id == self.bot.user.id):
            return

        if payload.channel_id != self.bot.config.get('stats_channel'):
            return
        self.bot.logger.info(payload.emoji)
        if str(payload.emoji) == '🔁':
            await self.create_stats()
            message = await self.bot.get_channel(self.bot.config.get('stats_channel')).fetch_message(payload.message_id)
            await message.remove_reaction(str(payload.emoji), await self.bot.fetch_user(payload.user_id))


    @timing(log=log)
    async def create_stats(self):
        await self.bot.load_cache()
        if self.last_stats and (datetime.now()-self.last_stats).total_seconds() < 30: return 
        reviewers = [x['user_id'] for x in self.bot.config['reviewer_channels']]
        channel = self.bot.get_channel(self.bot.config.get('stats_channel'))
        webhook = (await channel.webhooks())[0]
        if not self.stat_message:
            message = await webhook.send(content="Stats", wait=True)
            await (await channel.fetch_message(message.id)).add_reaction('🔁')
            self.stat_message = message.id
        data = {'method': 'update_stats', 'channel': self.bot.config.get('stats_channel'), 'message': self.stat_message, 'reviewers': reviewers, 'url': webhook.url}
        await self.bot.redis.rpush('flagbot:queue', json.dumps(data))
        self.last_stats = datetime.now()

    @commands.check(check_granted_server)
    @commands.command("stats")
    async def stats_command(self, ctx: commands.Context, field: str='', user: discord.User=None):
        conn = self.bot.get_db()
        fields = ['insult', 'severe_toxic', 'identity_hate', 'threat', 'nsfw']
        if field not in fields:
            await ctx.send(f"Sorry, thats not a valid category. The valid categories are **{', '.join(fields)}**")
            return

        if user is None:
            user = ctx.author
        messages = await conn.get_deviance_messages(user.id, field)
        not_voted_document = ' '.join([x['clean_content'] for x in messages if x['submitted'] == 0])
        wordlist = not_voted_document.split()
        unique_words = list(set(wordlist))
        worddict = {}
        for word in unique_words:
            if word != "__name__":
                worddict[word] = wordlist.count(word)
        worddict = dict(sorted(worddict.items(), key=lambda item: item[1]))

        last_reviews = list(reversed([x['clean_content'] for x in messages if x['submitted'] == 0]))[:10]
        message_text = f"__**{user.name}'s stats for {field}**__\n"
        message_text += f"Frequently missed words: ||{', '.join(list(reversed(list(worddict.keys())[-15:])))}||\n"
        message_text += f"__Last {len(last_reviews)} missed {field} reviews:__\n"
        message_text += '\n'.join([f"{i+1}. {x}" for i,x in enumerate(last_reviews)])

        await ctx.send(message_text)

def setup(bot):
    bot.add_cog(Stats(bot))

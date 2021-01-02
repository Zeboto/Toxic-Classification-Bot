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
        conn = self.bot.get_db()
        self.completed = await conn.get_total_reviews()
        reviewers = [x['user_id'] for x in self.bot.config['reviewer_channels']]
        for r in reviewers:
            user = self.bot.get_user(r) or await self.bot.fetch_user(r)
            total_score, scores = await conn.get_deviance(r)
            self.reviewer_stats[str(r)] = {
                'name': user.name,
                'completed': await conn.get_reviews_count(r),
                'left': await conn.get_remaining_reviews(r),
                'total_score': total_score,
                'scores': scores
            }
        self.remaining = max([x['left'] for x in self.reviewer_stats.values()])
        await self.update_embed()

    async def update_stats(self, user_id):
        if self.last_stats and (datetime.now() - self.last_stats).total_seconds() < 3 * 60:
            log.info("Skipping stats")
            return

        conn = self.bot.get_db()
        reviewers = [x['user_id'] for x in self.bot.config['reviewer_channels']]
        for r in reviewers:
            user = self.bot.get_user(r) or await self.bot.fetch_user(r)
            total_score, scores = await conn.get_deviance(r)
            self.reviewer_stats[str(r)]['completed'] = await conn.get_reviews_count(r)
            self.reviewer_stats[str(r)]['left'] = await conn.get_remaining_reviews(r)

        total_score, scores = await conn.get_deviance(user_id)
        self.reviewer_stats[str(user_id)]['total_score'] = total_score
        self.reviewer_stats[str(user_id)]['scores'] = scores
        self.remaining = max([x['left'] for x in self.reviewer_stats.values()])
        self.completed = await conn.get_total_reviews()
        await self.update_embed()
        self.last_stats = datetime.now()

    async def update_embed(self):
        content = f"Reviews Left: {self.remaining}\nReviews Completed: {self.completed}"

        embed = discord.Embed(
            title='Reviewer Stats',
            description=content,
            color=0xff0000
        )
        for uid, r in self.reviewer_stats.items():
            embed.add_field(
                name=r['name'], value=f"Reviews Left: {r['left']}\nReviews Completed: {r['completed']}\nDeviance Score: {r['total_score']}")

        channel = self.bot.get_channel(self.bot.config.get('stats_channel'))
        webhook = (await channel.webhooks())[0]
        if not self.stat_message:
            message = await webhook.send(embed=embed, avatar_url=self.bot.user.avatar_url, wait=True)
            self.stat_message = message.id
        else:
            await webhook.edit_message(self.stat_message, embed=embed)


def setup(bot):
    bot.add_cog(Stats(bot))

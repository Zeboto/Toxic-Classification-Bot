# -*- coding: utf-8 -*-

import asyncpg
import asyncio
import base64
import json
import logging
import os
import signal
import traceback
from discord import Webhook, AsyncWebhookAdapter
import aiohttp
import aioredis
import discord.http
import toml

from .db import get_stats,get_total_reviews
log = logging.getLogger(__name__)


WORKER_COUNT = int(os.environ.get('WORKER_COUNT', '3'))

CONNECTION_ERRORS = (
    asyncio.TimeoutError,
    aiohttp.ClientConnectionError,
    aiohttp.ClientConnectorError,
    aiohttp.ClientOSError,
    aiohttp.ServerConnectionError,
)


# Please ignore this ugliness
async def _yield_forever():
    while True:
        await asyncio.sleep(1)


class Worker:
    def __init__(self, config):
        self.config = config

        self.http = None
        self.session = None

        self.redis = None
        self.db = None
        self.db_available = asyncio.Event()
        self.token = None
        self.worker_id = None

        self._bot_user_id = int(base64.b64decode(self.config['token'].split('.', 1)[0]))
        
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.acquire_pool())
        
    async def acquire_pool(self):
        credentials = self.config["database"]

        if not credentials:
            log.critical("Cannot connect to db, no credentials!")
            await self.logout()
        
        self.db = await asyncpg.create_pool(**credentials)
        self.db_available.set()

    @classmethod
    def with_config(cls):
        """Create a bot instance with a Config."""

        with open('config.toml', 'r', encoding='utf-8') as fp:
            data = toml.load(fp)

        return cls(data)

    async def start(self):
        self.redis = await aioredis.create_redis_pool(**self.config['redis'])

        await self.claim_token()
        self._claim_task = self.loop.create_task(self._keep_claim())

        # We're using discord.py's HTTP class for rate limit handling
        # This is not intended to be used so there's no pretty way of creating it
        self.http = http = discord.http.HTTPClient()
        http._token(self.token)
        self.session = http._HTTPClient__session = aiohttp.ClientSession()

        self.loop.create_task(self.run_jobs())

        await _yield_forever()

    def run(self):
        loop = self.loop

        loop.create_task(self.start())

        try:
            loop.add_signal_handler(signal.SIGINT, loop.stop)
            loop.add_signal_handler(signal.SIGTERM, loop.stop)
        except RuntimeError:  # Windows
            pass

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            loop.stop()

    async def claim_token(self):
        # We have a token per active worker
        # As we don't know which worker we are we simply claim a token by setting a key in redis
        # If it's set we can assume it to be currently used (unless the worker crashed - but it'll expire)
        # Should we not find a free token we'll simply wait for 10 seconds and try again

        while self.token is None:
            for worker_id in range(WORKER_COUNT):
                if await self.redis.execute('SET', f'flagbot:worker:{worker_id}', 'Worker', 'NX', 'EX', '30'):
                    self.worker_id = worker_id
                    self.token = self.config['workers'][worker_id]
                    break

            if self.token is None:
                log.warning('Failed to claim worker ID, retrying in 10 seconds ..')
                await asyncio.sleep(10)

    async def _keep_claim(self):
        while not self.loop.is_closed():
            try:
                with await self.redis as conn:
                    await conn.set(f'flagbot:worker:{self.worker_id}', ':ablobwavereverse:', expire=30)
            except (aioredis.ConnectionClosedError, aioredis.ProtocolError, aioredis.ReplyError, TypeError):
                log.exception('Failed to continue worker ID claim, retrying in 10 seconds ..')

            await asyncio.sleep(10)

    async def run_jobs(self):
        while self.loop.is_running():
            _, data = await self.redis.blpop('flagbot:queue')

            job = json.loads(data)
            log.info(f'Running job {job}.')

            try:
                await self.run_job(job)
            except Exception:
                log.exception(f'Failed to run job: {job}.')

    async def run_job(self, data):
        
        async def delete_reactions():
            channel_id = data['channel'] 
            message_id = data['message']
            emoji = data['emoji']
            try:
                users = await self.http.get_reaction_users(channel_id, message_id, emoji, 10)
                for u in users:
                    if u['id'] != str(self._bot_user_id):
                        await self.http.remove_reaction(channel_id, message_id, emoji, u['id'])
            except (Exception, *CONNECTION_ERRORS):  # Catch bare Exception to be safe
                return
        
        async def update_stats():
            reviewers = data['reviewers']
            log.critical(self.db)
            completed = await get_total_reviews(self.db)
            reviewer_stats = {}
            stats = await get_stats(self.db, self.config['min_votes'])
            for r in reviewers:
                user = await self.http.get_user(r)
                stat = [x for x in stats if r == x['user_id']][0]
                reviewer_stats[str(r)] = {
                    'name': user['username'],
                    'completed': stat['completed'],
                    'left': stat['remaining'],
                    'total_score': stat['total']
                }
            remaining = max([x['left'] for x in reviewer_stats.values()])
            await update_embed(completed, remaining, reviewer_stats)

        async def update_embed(completed, remaining, reviewer_stats):
            channel_id = data['channel'] 
            message_id = data['message']
            webhook_url = data['url']
            
            
            content = f"Reviews Left: {remaining}\nReviews Completed: {completed}"

            embed = discord.Embed(
                title='Reviewer Stats',
                description=content,
                color=0xff0000
            )
            for uid,r in reviewer_stats.items():
                embed.add_field(name=r['name'], value=f"Reviews Left: {r['left']}\nReviews Completed: {r['completed']}\nDeviance Score: {r['total_score']}")
            
            webhook = Webhook.from_url(webhook_url, adapter=AsyncWebhookAdapter(self.session))
            await webhook.edit_message(message_id, embed=embed)

        if data['method'] == 'delete_reactions':
            await delete_reactions()
        if data['method'] == 'update_stats':
            await update_stats()
        
    async def _send_error(self, message, channel_id):
        try:
            await self.http.send_message(channel_id, message)
        except discord.HTTPException:
            pass

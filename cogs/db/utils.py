# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta

import discord
import toml
from discord.ext import commands


class Rollback(Exception):
    pass


class DBUtils(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
            

    # ===================== #
    # ======= CACHE ======= #
    # ===================== #
    async def load_scan_channels(self):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetch("SELECT channel_id FROM scan_channels WHERE active")
            return [x['channel_id'] for x in record]

    async def load_reviewer_channels(self):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetch("SELECT user_id,channel_id FROM reviewers WHERE active")
            return [dict(x) for x in record]
    async def add_reviewer(self, user_id: int, channel_id: int):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    INSERT INTO reviewers (user_id, channel_id)
                    VALUES ($1, $2)
                    """,
                    user_id,
                    channel_id
                )
                

    async def add_score(self, scanned_content: str, scores: dict):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow(
                    """
                    INSERT INTO scores (scanned_content, insult, severe_toxic, identity_hate, threat, nsfw)
                    VALUES ($1, $2::REAL, $3::REAL, $4::REAL, $5::REAL, $6::REAL)
                    RETURNING id
                    """,
                    scanned_content,
                    scores['insult'],
                    scores['severe_toxic'],
                    scores['identity_hate'],
                    scores['threat'],
                    scores['nsfw']
                )
                return record['id']
    
    async def add_review_message(self, scanned_content: str, scores: dict):
        score_id = await self.add_score(scanned_content,scores)
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow(
                    """
                    INSERT INTO review_messages (score_id, clean_content)
                    VALUES ($1, $2)
                    """,
                    score_id,
                    scanned_content
                )
                return record['id']
    
    async def edit_review_message(self, review_id, clean_content: str):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    UPDATE review_messages
                    SET clean_content = $2
                    WHERE id = $1
                    """,
                    review_id,
                    clean_content
                )
                await conn.fetch(
                    """
                    DELETE FROM review_log
                    WHERE review_id = $1
                    """,
                    review_id
                )
                
    
            
def setup(bot):
    bot.add_cog(DBUtils(bot))


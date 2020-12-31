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



    # ====================== #
    # ======= CHECKS ======= #
    # ====================== #
    async def has_empty_queue(self, user_id: int):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(
                """
                SELECT COUNT(*) FROM review_log WHERE user_id = $1 
                """,
                user_id
            )
            return record['count'] != 0



    # ======================== #
    # ======= REVIEWER ======= #
    # ======================== #
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
    async def remove_reviewer(self, user_id: int):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    UPDATE reviewers
                    SET active = FALSE
                    WHERE user_id = $1
                    """,
                    user_id
                )

    # ===================== #
    # ======= SCORE ======= #
    # ===================== #
    async def get_score(self, score_id: int):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(
                    """
                    SELECT insult, severe_toxic, identity_hate, threat, nsfw
                    FROM scores
                    WHERE id = $1
                    """,
                    score_id
            )
            return record
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
    


    # ====================== #
    # === REVIEW MESSAGE === #
    # ====================== #
    async def add_review_message(self, scanned_content: str, scores: dict):
        score_id = await self.add_score(scanned_content,scores)
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow(
                    """
                    INSERT INTO review_messages (score_id, clean_content)
                    VALUES ($1, $2)
                    RETURNING *
                    """,
                    score_id,
                    scanned_content
                )
                return record['id']
    async def get_review_message(self, message_id, user_id):
        async with self.bot.db.acquire() as conn:
            self.bot.logger.info(message_id)
            record = await conn.fetchrow(
                    """
                    SELECT review_id, clean_content
                    FROM review_log INNER JOIN review_messages ON id = review_id
                    WHERE message_id = $1 AND user_id = $2 AND review_log.active
                    """,
                    message_id, user_id
            )
            self.bot.logger.info(record)
            return record
    async def edit_review_message(self, review_id, clean_content: str):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    UPDATE review_messages
                    SET clean_content = $2, in_sanitize = FALSE
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


    
    # ====================== # 
    # ==== REVIEW QUEUE ==== #
    # ====================== #
    async def find_empty_queues(self):
       async with self.bot.db.acquire() as conn:
            record = await conn.fetch(
                """
                SELECT user_id, channel_id
                FROM reviewers r
                WHERE NOT EXISTS(
                    SELECT *
                    FROM review_log
                    WHERE user_id = r.user_id AND active
                );
                """
            )
            return record

    async def pop_review_queue(self, user_id: int):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(
                """
                SELECT *
                FROM review_messages r
                WHERE in_sanitize = FALSE AND active AND NOT EXISTS(
                    SELECT *
                    FROM review_log
                    WHERE user_id = $1 AND review_id = r.id AND active = FALSE
                );
                """,
                user_id
            )
            self.bot.logger.info(record)
            return record

    async def get_active_queue_messages(self, review_id: int):
        async with self.bot.db.acquire() as conn:                
            record = await conn.fetch(
                """
                SELECT message_id,review_log.user_id,channel_id
                FROM review_log INNER JOIN reviewers ON review_log.user_id = reviewers.user_id
                WHERE review_id = $1 AND review_log.active = TRUE
                """,
                review_id
            )
            return record


    # ====================== # 
    # ===== REVIEW LOG ===== #
    # ====================== #
    async def add_review_log(self, review_id: int, user_id: int, message_id: int):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    INSERT INTO review_log (review_id, user_id, message_id)
                    VALUES ($1, $2, $3) 
                    """,
                    review_id,
                    user_id,
                    message_id
                )

    async def remove_review_log(self, review_id: int):
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.fetch(
                    """
                    DELETE FROM review_log
                    WHERE review_id = $1
                    """,
                    review_id
                )
    

    # ============================= # 
    # ===== REVIEW SUBMISSION ===== #
    # ============================= #
    async def submit_review(self, review_id: int, user_id: int, scores: dict):
        self.bot.logger.info("Submitting review")
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetch(
                    """
                    UPDATE review_log
                    SET insult = $3::SMALLINT, severe_toxic = $4::SMALLINT, identity_hate = $5::SMALLINT, threat = $6::SMALLINT, nsfw = $7::SMALLINT, active = FALSE
                    WHERE review_id = $1 and user_id = $2
                    RETURNING *
                    """,
                    review_id,
                    user_id,
                    scores['insult'],
                    scores['severe_toxic'],
                    scores['identity_hate'],
                    scores['threat'],
                    scores['nsfw'],
                )
                self.bot.logger.info(record)
    async def check_complete_review(self, review_id: int):
        async with self.bot.db.acquire() as conn:                
            record = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM review_log
                    WHERE review_id = $1 AND active = FALSE
                    """,
                    review_id
            )
            if record >= self.bot.config.get('min_votes'):
                record = await conn.fetch(
                    """
                    SELECT clean_content, insult, severe_toxic, identity_hate, threat, nsfw
                    FROM review_log 
                    INNER JOIN review_messages ON review_id = id
                    WHERE review_id = $1
                    """,
                    review_id
                )
                new_scores = {
                    'insult': 0,
                    'severe_toxic': 0,
                    'identity_hate': 0, 
                    'threat': 0,
                    'nsfw': 0
                }
                for r in record:
                    for k, v in new_scores.items():
                        new_scores[k] += r[k]    
                for k, v in new_scores.items():
                    new_scores[k] = 1 if new_scores[k] / len(record) >= 2/3 else 0
                await self.complete_review(review_id)
                return {'message': record[0]['clean_content'], 'score': new_scores}
            return None
    
    async def complete_review(self, review_id: int):
        async with self.bot.db.acquire() as conn:                
            async with conn.transaction():
                await conn.fetchval(
                    """
                    UPDATE review_log
                    SET active = FALSE
                    WHERE review_id = $1
                    """,
                    review_id
                )
                await conn.fetchval(
                    """
                    UPDATE review_messages
                    SET active = FALSE
                    WHERE id = $1
                    """,
                    review_id
                )
    

    
    # ====================== # 
    # ====== SANITIZE ====== #
    # ====================== #
    async def set_sanitize(self, review_id: int):
        async with self.bot.db.acquire() as conn:                
            async with conn.transaction():
                await conn.fetch(
                    """
                    UPDATE review_messages
                    SET in_sanitize = TRUE
                    WHERE id = $1
                    """,
                    review_id
                )
        record = await self.get_active_queue_messages(review_id)
        await self.remove_review_log(review_id)
        return record
                    



def setup(bot):
    bot.add_cog(DBUtils(bot))


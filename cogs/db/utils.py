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
        score_id = await self.add_score(scanned_content, scores)
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
            record = await conn.fetchrow(
                """
                    SELECT review_id, clean_content
                    FROM review_log INNER JOIN review_messages ON id = review_id
                    WHERE message_id = $1 AND user_id = $2 AND review_log.active
                    """,
                message_id, user_id
            )
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
    
    async def delete_active_review_message(self, user_id):
        async with self.bot.db.acquire() as conn:
            await conn.fetch(
                """
                    DELETE FROM review_log
                    WHERE user_id = $1 AND active
                    """,
                user_id
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
                WHERE in_sanitize = FALSE 
                AND active 
                AND NOT EXISTS(
                    SELECT *
                    FROM review_log
                    WHERE user_id = $1 AND review_id = r.id AND active = FALSE
                )
                AND NOT r.id IN (
                    SELECT review_id
                    FROM review_log
                    GROUP BY review_id HAVING COUNT(*) >= $2
                )
                ORDER BY r.id ASC 
                """,
                user_id,
                self.bot.config.get('min_votes')
            )
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
                    new_scores[k] = 1 if new_scores[k] / len(record) >= 2 / 3 else 0
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

    # ===================== #
    # ======= STATS ======= #
    # ===================== #

    async def get_total_reviews(self):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchval("SELECT COUNT(*) FROM review_messages WHERE active = FALSE AND in_sanitize = FALSE")
            return record

    async def get_reviews_count(self, user_id):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchval("SELECT COUNT(*) FROM review_log WHERE active = FALSE AND user_id = $1", user_id)
            return record

    async def get_deviance(self, user_id):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(
                """
                WITH reviews_table AS (
                    SELECT * 
                    FROM review_log INNER JOIN review_messages ON id = review_id 
                    WHERE review_log.active = FALSE 
                    AND review_messages.active = FALSE 
                    AND in_sanitize = FALSE 
                    AND EXISTS (
                        SELECT 1
                        FROM review_log
                        WHERE review_messages.id = review_id 
                        AND user_id = $1
                        AND active = FALSE
                    )
                ), result_table AS (
                    SELECT 
                        review_id,
                        CASE WHEN AVG(insult) > 2/3 THEN 1 ELSE 0 END insult,
                        CASE WHEN AVG(severe_toxic) > 2/3 THEN 1 ELSE 0 END severe_toxic,
                        CASE WHEN AVG(identity_hate) > 2/3 THEN 1 ELSE 0 END identity_hate,
                        CASE WHEN AVG(threat) > 2/3 THEN 1 ELSE 0 END threat,
                        CASE WHEN AVG(nsfw) > 2/3 THEN 1 ELSE 0 END nsfw
                    FROM reviews_table
                    GROUP BY review_id
                ), user_table AS (
                    SELECT *
                    FROM reviews_table
                    WHERE user_id = $1
                )
                SELECT
                    ROUND(AVG(CASE WHEN result_table.insult = user_table.insult THEN 0 ELSE 1 END), 3) AS insult,
                    ROUND(AVG(CASE WHEN result_table.severe_toxic = user_table.severe_toxic THEN 0 ELSE 1 END), 3) AS severe_toxic,
                    ROUND(AVG(CASE WHEN result_table.identity_hate = user_table.identity_hate THEN 0 ELSE 1 END), 3) AS identity_hate,
                    ROUND(AVG(CASE WHEN result_table.threat = user_table.threat THEN 0 ELSE 1 END), 3) AS threat,
                    ROUND(AVG(CASE WHEN result_table.nsfw = user_table.nsfw THEN 0 ELSE 1 END), 3) AS nsfw
                FROM result_table INNER JOIN user_table USING(review_id)
                """,
                user_id)
            return int(sum(record.values()) * 1000), dict(record)

    async def get_remaining_reviews(self, user_id: int):
        async with self.bot.db.acquire() as conn:
            record = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM review_messages r
                WHERE in_sanitize = FALSE 
                AND active 
                AND NOT EXISTS(
                    SELECT *
                    FROM review_log
                    WHERE user_id = $1 AND review_id = r.id AND active = FALSE
                )
                AND NOT r.id IN (
                    SELECT review_id
                    FROM review_log
                    GROUP BY review_id HAVING COUNT(*) >= $2
                )
                """,
                user_id,
                self.bot.config.get('min_votes')
            )
            return record
    
    
    # ======================= #
    # ===== INFRACTIONS ===== #
    # ======================= #

    async def add_infractions(self, infractions):
        infs = []
        for inf in infractions:
            infs.append((
                None, 
                inf['message'].author.id, 
                inf['message'].guild.id, 
                inf['message'].channel.id, 
                inf['message'].id, 
                await self.add_score(inf['message'].content, inf['score']), 
                None
            ))

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetch(
                    """
                    INSERT INTO infractions (user_id, server_id, channel_id, message_id, score_id)
                    (SELECT 
                        i.user_id, i.server_id, i.channel_id, i.message_id, i.score_id
                    FROM
                        unnest($1::infractions[]) as i
                    )
                    """,
                    infs
                )

def setup(bot):
    bot.add_cog(DBUtils(bot))

import asyncio
from datetime import datetime, timedelta

import discord
import toml
from discord.ext import commands


# ===================== # 
# ======= CACHE ======= #
# ===================== #
async def load_reviewer_channels(self):
    async with self.bot.db.acquire() as conn:
        record = await conn.fetch("SELECT user_id,channel_id FROM reviewers WHERE active")
        return [dict(x) for x in record]


# ===================== # 
# ======= STATS ======= #
# ===================== #

async def get_total_reviews(db):
    async with db.acquire() as conn:
        record = await conn.fetchval("SELECT COUNT(*) FROM review_messages WHERE active = FALSE AND in_sanitize = FALSE")
        return record

async def get_remaining_reviews(db, user_id: int, min_votes):
    async with db.acquire() as conn:
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
            min_votes
        )
        return record

async def get_stats(db, min_votes):
    async with db.acquire() as conn:
        record = await conn.fetch(
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
                    AND active = FALSE
                    GROUP BY user_id
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
            ), deviance_table as (
                SELECT
                    user_id,
                    COUNT(*) as completed,
                    ROUND(AVG(CASE WHEN result_table.insult = reviews_table.insult THEN 0 ELSE 1 END), 3) AS insult,
                    ROUND(AVG(CASE WHEN result_table.severe_toxic = reviews_table.severe_toxic THEN 0 ELSE 1 END), 3) AS severe_toxic,
                    ROUND(AVG(CASE WHEN result_table.identity_hate = reviews_table.identity_hate THEN 0 ELSE 1 END), 3) AS identity_hate,
                    ROUND(AVG(CASE WHEN result_table.threat = reviews_table.threat THEN 0 ELSE 1 END), 3) AS threat,
                    ROUND(AVG(CASE WHEN result_table.nsfw = reviews_table.nsfw THEN 0 ELSE 1 END), 3) AS nsfw
                FROM result_table INNER JOIN reviews_table USING(review_id)
                GROUP BY user_id
            )
            SELECT *, 
                ((insult + severe_toxic + identity_hate + threat + nsfw)*1000)::SMALLINT as total 
            FROM deviance_table
            """
        )
        ret_value = []
        for x in record:
            x = dict(x)
            x['remaining'] = await get_remaining_reviews(db,x['user_id'],min_votes)
            ret_value.append(x)
        return ret_value
        

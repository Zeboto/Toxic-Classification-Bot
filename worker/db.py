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

async def get_total_remaining_reviews(db):
    async with db.acquire() as conn:
        record = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM review_messages r
            WHERE in_sanitize = FALSE 
            AND active
            """
        )
        return record
 	
async def get_stats(db, config):
    async with db.acquire() as conn:
        record = await conn.fetch(
            """
            WITH active_review_table AS (
                SELECT *
                FROM review_messages 
                WHERE active 
                AND NOT in_sanitize
            ), review_count_table AS (
                SELECT review_id
                FROM review_log 
                GROUP BY review_id HAVING COUNT(*) < $1
            ), free_review_table AS (
                SELECT id FROM active_review_table
                WHERE id IN (SELECT review_id FROM review_count_table)
            ), active_queue_table AS (
                SELECT user_id, COUNT(*) AS active_count
                FROM review_log 
                WHERE active
                GROUP BY user_id
            ), inactive_queue_table AS (
                SELECT user_id, COUNT(*) AS inactive_count
                FROM review_log 
                WHERE review_id IN (SELECT id FROM free_review_table)
                GROUP BY user_id
            ), final_query AS (
                SELECT user_id, (free_review_count+active_count-inactive_count) AS remaining
                FROM (SELECT user_id, COALESCE(MAX(active_count), 0) active_count, COALESCE(MAX(inactive_count), 0) inactive_count
                            FROM active_queue_table FULL JOIN inactive_queue_table USING(user_id)
                            GROUP BY user_id
                        
                    ) k, (SELECT COALESCE(MAX(free_review_count), 0) free_review_count FROM (SELECT COUNT(*) AS free_review_count FROM free_review_table) f) r
            ), reviews_table AS (
                SELECT * 
                FROM review_log INNER JOIN review_messages ON id = review_id 
                WHERE review_log.active = FALSE 
                AND review_messages.active = FALSE 
                AND in_sanitize = FALSE 
            ), decision_table AS (
                SELECT 
                    review_id,
                    CASE WHEN AVG(insult) > 2/3 THEN 1 ELSE 0 END insult,
                    CASE WHEN AVG(severe_toxic) > 2/3 THEN 1 ELSE 0 END severe_toxic,
                    CASE WHEN AVG(identity_hate) > 2/3 THEN 1 ELSE 0 END identity_hate,
                    CASE WHEN AVG(threat) > 2/3 THEN 1 ELSE 0 END threat,
                    CASE WHEN AVG(nsfw) > 2/3 THEN 1 ELSE 0 END nsfw
                FROM (
                        SELECT * FROM reviews_table
                        UNION 
                        SELECT * 
                        FROM reviews_table
                        WHERE trusted_review
                    ) votes
                GROUP BY review_id
            ), deviance_table as (
                SELECT
                    user_id,
                    COUNT(*) as completed,
                    ROUND(AVG(CASE WHEN decision_table.insult = reviews_table.insult THEN 0 ELSE 1 END), 3) AS insult,
                    ROUND(AVG(CASE WHEN decision_table.severe_toxic = reviews_table.severe_toxic THEN 0 ELSE 1 END), 3) AS severe_toxic,
                    ROUND(AVG(CASE WHEN decision_table.identity_hate = reviews_table.identity_hate THEN 0 ELSE 1 END), 3) AS identity_hate,
                    ROUND(AVG(CASE WHEN decision_table.threat = reviews_table.threat THEN 0 ELSE 1 END), 3) AS threat,
                    ROUND(AVG(CASE WHEN decision_table.nsfw = reviews_table.nsfw THEN 0 ELSE 1 END), 3) AS nsfw
                FROM decision_table INNER JOIN reviews_table USING(review_id)
                GROUP BY user_id
            ), result_query as (
                SELECT *, 
                    ((insult + severe_toxic + identity_hate + threat + nsfw)*1000)::SMALLINT as total 
                FROM deviance_table
            ), trusted_query as (
                UPDATE reviewers 
                SET trusted = (completed > $2 AND total < $3) 
                FROM result_query
                WHERE reviewers.user_id = result_query.user_id
            )
            SELECT * FROM result_query INNER JOIN reviewers USING (user_id) INNER JOIN final_query USING (user_id) ORDER BY reviewers.date_created ASC
            """,
            config['min_votes'],
            config['trusted_reviewer']['min_reviews'],
            config['trusted_reviewer']['max_deviance']
        )
        ret_value = []
        for x in record:
            x = dict(x)
            ret_value.append(x)
        return ret_value
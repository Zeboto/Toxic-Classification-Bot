# -*- coding: utf-8 -*-
import csv
import math
import os
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from utils.checks import in_reviewer_channel


class Rollback(Exception):
    pass


class ReviewQueue(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        
        self.review_queue = []
        self.in_review = []
        self.review_lock = asyncio.Lock()
        self.messages = []
        self.cols_target = ['insult','severe_toxic','identity_hate','threat','nsfw']
        asyncio.create_task(self.clean_channel())

    
    async def clean_channel(self):
        await self.bot.wait_until_ready()
        # Clear review queue
        channel = self.bot.get_channel(self.bot.config.get('review_channel'))
        await channel.purge(limit=100)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent ):
        
        # Ignore reactions from the bot
        if (payload.user_id == self.bot.user.id): return

        # Ignore reactions not in review
        if not in_reviewer_channel(self, {'user_id': payload.user_id, 'channel_id': payload.channel_id}): return
        
        self.bot.logger.info("Logged reaction")

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        
        reaction = [r for r in message.reactions if str(r.emoji) == str(payload.emoji)][0]
        member = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)

        emojis = self.bot.config.get('reaction_emojis')
        min_votes = self.bot.config.get('min_votes')
        # Ignore feature scoring options
        if str(reaction) not in emojis[-4:]: return    
        
        
        
        # Complete review when votes reached
        if str(reaction) == emojis[-4]:
            self.bot.logger.info("Sending review.")
            async with self.review_lock:
                conn = self.bot.get_db()
                review = await conn.get_review_message(message.id, member.id)
                if review is None: return
                reactions = message.reactions
                scores = dict()
                for r in reactions:
                    if str(r) in emojis[:-4]:
                        i = emojis.index(str(r)) 
                        scores[self.cols_target[i]] = r.count-1
                await conn.submit_review(review['review_id'], member.id, scores)
                complete_review = await conn.check_complete_review(review['review_id'])
                if complete_review:
                    self.add_train_row(complete_review)
                
                await self.change_message(message, member)
        
        # Send to santization queue
        elif str(reaction) == emojis[-3]:
            self.bot.logger.info("Sending to santization queue")
            async with self.review_lock:
                conn = self.bot.get_db()
                review = await conn.get_review_message(message.id,member.id)    
                if review is None: return
                sanitize_cog = self.bot.get_cog('SanitizeQueue')
                if sanitize_cog is None:
                    self.bot.logger.info("The cog \"SanitizeQueue\" is not loaded")
                    return
                await sanitize_cog.add_to_sanitize_queue(review)
            
                
    async def change_message(self, message, member):
        conn = self.bot.get_db()
        review_message = await conn.pop_review_queue(member.id)
        
        if review_message:
            scores = await conn.get_score(review_message['score_id'])
            embed = self.create_review_embed(review_message['clean_content'], scores)
            await message.edit(embed=embed)
            
            await conn.add_review_log(review_message['id'], member.id, message.id)
            
            for r in message.reactions:
                users = await r.users().flatten()
                for u in users:
                    if u.id != self.bot.user.id:
                        await message.remove_reaction(r.emoji, u)
        else:
            await message.delete()
    def add_train_row(self, row: dict={'message': str, 'score': dict}):
        row = ([row['message']] + [x[1] for x in row['score'].items()])
        is_new_file = not os.path.exists("./input/new_train.csv")
            
        with open(r'./input/new_train.csv', 'a') as f:
            writer = csv.writer(f)
            if is_new_file:
                writer.writerow(['comment_text'] + self.cols_target)
            writer.writerow(row)

    async def create_new_review(self, review: dict={'message': str, 'score': {'insult': int, 'severe_toxic': int, 'identity_hate': int, 'threat': int}}):
        message = review['message']
        scores = review['score']
        
        conn = self.bot.get_db()
        
        await conn.add_review_message(message, scores)
        
        await self.fill_empty_queues()
        

    async def fill_empty_queues(self):
        conn = self.bot.get_db()
        
        reviewers = await conn.find_empty_queues()

        if len(reviewers) == 0:
            return

        for reviewer in reviewers:
            review_message = await conn.pop_review_queue(reviewer['user_id'])
            if not review_message: continue
            channel = self.bot.get_channel(reviewer['channel_id'])
            scores = await conn.get_score(review_message['score_id'])
            
            embed = self.create_review_embed(review_message['clean_content'], scores)
            
            sent_message = await channel.send(embed=embed)

            await conn.add_review_log(review_message['id'], reviewer['user_id'], sent_message.id)

            for emoji in self.bot.config.get('reaction_emojis')[:-2]:
                await sent_message.add_reaction(emoji)
            

        


    def create_review_embed(self, content: str, scores: dict):
        score_values = []

        for i, (k, v) in enumerate(scores.items()):
            score_values.append(f"{self.bot.config.get('reaction_emojis')[i]} {round(v,2)}")

        embed = discord.Embed(
            title='Review Message',
            description=content,
            color=0xff0000
        )
        embed.add_field(name='Scores', value='||' + ' '.join(score_values) + '||')
        return embed

    async def add_reviews_to_queue(self, new_reviews):
        nlp_cog = self.bot.get_cog('NLP')
        if nlp_cog is None:
            self.bot.logger.info("The cog \"NLP\" is not loaded")
            return
        for r in new_reviews:
            r['message'] = nlp_cog.clean_text(r['message'].content if type(r['message']) is not str else r['message'])
            await self.create_new_review(r)
                
                    
                    
    
    
            
def setup(bot):
    bot.add_cog(ReviewQueue(bot))


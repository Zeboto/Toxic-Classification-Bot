# -*- coding: utf-8 -*-
import pickle
import numpy as np
import pandas as pd
import seaborn as sns
import asyncio
import collections
import io
import os
import math
import random
import re
import csv
import math
from datetime import datetime, timedelta
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

import discord
import toml
from discord.ext import commands

from cogs.utils import *
class Rollback(Exception):
    pass


class FlagScanner(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        
        self.compute_lock = asyncio.Lock()

        self.queue_lock = asyncio.Lock()
        self.review_queue = []
        self.in_review = []
        self.sanitize_queue = []
        self.sanitize_message = None
        
        self.messages = []
        self.cols_target = ['insult','severe_toxic','identity_hate','threat']
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.remove_command('help')
        
        # Clear review queue
        channel = self.bot.get_channel(self.bot.config.get('review_channel'))
        await channel.purge(limit=100)

        # Clear sanitize channel
        channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
        await channel.purge(limit=100)
 
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore prefix
        if message.content.startswith("f."): return
        
        if (message.author.id == self.bot.user.id): return

        if in_sanitize_channel(self, message):
            await message.delete()
            await self.update_sanitize(message)

        # Ignore message not in scan channels
        if not in_scan_channel(self, message): return
        
        # Keep queue messages loaded
        for m in self.in_review:
            if m['review'].id not in [x.id for x in self.bot.cached_messages]:
                await self.bot.get_channel(self.bot.config.get('review_channel')).fetch_message(m['review'].id)

        # Keep sanitize message loaded
        if self.sanitize_message is not None and self.sanitize_message['sanitize'].id not in [x.id for x in self.bot.cached_messages]:
            await self.bot.get_channel(self.bot.config.get('review_channel')).fetch_message(self.sanitize_message['sanitize'].id)
        
        async with self.compute_lock:
            # Add messages to processing queue
            self.messages += [message]
            self.bot.logger.info(f"Added message {len(self.messages)}/{100}")

            # If enough messages were collected then start processing
            if len(self.messages) == 100:
                flags,new_reviews = await asyncio.get_event_loop().run_in_executor(None, self.compute_messages)
                if len(flags) == 0: return
                
                # Send flagged messages
                for flag in flags:
                    await self.bot.get_channel(self.bot.config.get('flag_channel')).send(embed=flag)
                
                # Add flagged messages to review queue
                await self.add_reviews_to_queue(new_reviews)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent ):
        
        # Ignore reactions from the bot
        if (payload.user_id == self.bot.user.id): return

        # Ignore reactions not in review or sanitize channels
        if not in_review_channel(self, payload.channel_id) and not in_sanitize_channel(self, payload.channel_id): return
        
        self.bot.logger.info("Logged reaction")
        
        emojis = self.bot.config.get('reaction_emojis')
        message = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        reaction = next(r for r in message.reactions if str(r.emoji) == str(payload.emoji))


        # Ignore feature scoring options
        if str(reaction) not in emojis[-4:]: return    
        
        # Complete review when votes reached
        if in_review_channel(self, message) and str(reaction) == emojis[-4] and reaction.count > 3:
            self.bot.logger.info("Sending review.")
            async with self.queue_lock:
                review_message = next(x for x in self.in_review if x['review'].id == message.id)
                self.in_review.pop(self.in_review.index(review_message))
                reactions = message.reactions
                for r in reactions:
                    if str(r) in emojis[:-4]:
                        i = emojis.index(str(r)) 
                        review_message['score'][self.cols_target[i]] = 1 if (r.count-1) >= math.ceil((reaction.count-1)*2/3) else 0
                
                self.add_train_row(review_message)
                await message.delete()

                # Add new message to queue
                if len(self.review_queue) > 0:
                    new_review = self.review_queue.pop()
                    new_review['review'] = await self.create_new_review(new_review)
                    self.in_review.append(new_review)
        
        # Send to santization queue
        if in_review_channel(self, message) and str(reaction) == emojis[-3]:
            self.bot.logger.info("Sending to santization queue")
            async with self.queue_lock:
                review_message = next(x for x in self.in_review if x['review'].id == message.id)
                self.in_review.pop(self.in_review.index(review_message))
                self.sanitize_queue.insert(0, review_message)
                await review_message['review'].delete()
                if self.sanitize_message is None:
                    await self.create_new_sanitize()
        
        # Approve sanitize message
        if in_sanitize_channel(self, message) and str(reaction) == emojis[-2]:
            sanitize = self.sanitize_message
            async with self.queue_lock:
                self.sanitize_message = None
            sanitize['message'] = sanitize['sanitize'].embeds[0].description
            await self.add_reviews_to_queue([sanitize])
            await sanitize['sanitize'].delete()
            if len(self.sanitize_queue) > 0:
                await self.create_new_sanitize()
                new_review = self.review_queue.pop()
                new_review['review'] = await self.create_new_review(new_review)
                self.in_review.append(new_review)
        
        # Delete sanitize message 
        if in_sanitize_channel(self, message) and str(reaction) == emojis[-1]:
            sanitize = self.sanitize_message
            async with self.queue_lock:
                self.sanitize_message = None
            await sanitize['sanitize'].delete()
            if len(self.sanitize_queue) > 0:
                await self.create_new_sanitize()
            
    @commands.is_owner()
    @commands.command("extract_messages")
    async def extract_messages_command(self, ctx: commands.Context, channel_id: str='', count: int=100):
        channel = self.bot.get_channel(int(channel_id))
        messages = await channel.history(limit=count).flatten()
        
        async with self.compute_lock:
            self.messages += messages
            self.bot.logger.info(f"Added message {len(self.messages)}/{100}")
            if len(self.messages) >= 100:
                flags,new_reviews = await asyncio.get_event_loop().run_in_executor(None, self.compute_messages)
                if len(flags) == 0: return
                for flag in flags:
                    await self.bot.get_channel(self.bot.config.get('flag_channel')).send(embed=flag)
                await self.add_reviews_to_queue(new_reviews)
            
    def compute_messages(self):
        test_messages = self.messages.copy()
        self.bot.logger.info([x.content for x in test_messages])
        self.messages = []
        self.bot.logger.info(f"Starting evaluation on {len(test_messages)} messages...")

        start = datetime.now()
        
        train_df = pd.read_csv('./input/train.csv')
        if os.path.exists("./input/new_train.csv"):
            train_df = pd.concat([pd.read_csv('./input/new_train.csv'),train_df], axis=0, ignore_index=True)
            
        X = train_df.comment_text

        data = {'comment_text': [clean_text(x.content) for x in test_messages]}
        test_df = pd.DataFrame(data=data)

        vect = TfidfVectorizer(ngram_range=(1,2), stop_words='english',
                    min_df=3, max_df=0.9, smooth_idf=1, sublinear_tf=1)
        message_contents = test_df.comment_text
        train_X = vect.fit_transform(X)
        test_X = vect.transform(message_contents)
        logreg = LogisticRegression(C=12.0, solver='liblinear')
        results = dict()
        for i in range(len(test_df)):
            results[i] = {}
        for label in self.cols_target:
            self.bot.logger.info('... Processing {}'.format(label))
            y = train_df[label]
            # train the model using X_dtm & y
            logreg.fit(train_X, y)
            # compute the predicted probabilities for X_test_dtm
            test_y_prob = logreg.predict_proba(test_X)[:,1]
            for i,x in enumerate(test_y_prob):
                results[i][label] = x
        self.bot.logger.info(f"Took {(datetime.now()-start).total_seconds()} seconds!")
        flagged_messages = []
        random_non_flagged_messages = []
        for k,v in results.items():
            if clean_text(test_messages[k].content) == "":
                continue
            if any([value > 0.5 for key,value in v.items()]):
                flagged_messages.append({'message':test_messages[k],'score':v})
            elif (random.random() <= 0.01):
                random_non_flagged_messages.append({'message':test_messages[k],'score':v})

        self.bot.logger.info(f"Flagged {len(flagged_messages)} messages.")
        embeds = []
        if len(flagged_messages) == 0: return []
        for flagged_message in flagged_messages:
            message = flagged_message['message']
            scores = flagged_message['score']
            description = f"**User**: ||{message.author.name}#{message.author.discriminator} (`{message.author.id}`)||\n**Message**: [{message.content}]({message.jump_url})\n\n__**Scores:**__\n"
            for k,v in scores.items():
                description += f"`{k}`: {round(v,3)}\n"

            embed = discord.Embed(
                title='New Flagged Message!',
                description=description,
                color=0xff0000
            )
            embed.set_thumbnail(url=message.guild.icon_url_as(format="gif",static_format="png"))
            embeds.append(embed)
        if len(flagged_messages) > 0:
            return embeds, (flagged_messages + random_non_flagged_messages)
        
    def add_train_row(self, row: dict={'message': str, 'score': {'insult': int, 'severe_toxic': int, 'identity_hate': int, 'threat': int}}):
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
        description = f"**Message**: {message}\n\n__**Scores:**__\n"
        index = 0
        for k,v in scores.items():
            description += f"{self.bot.config.get('reaction_emojis')[index]} `{k}`: ||{round(v,3)}||\n"
            index += 1
        
        embed = discord.Embed(
            title='Review Message',
            description=description,
            color=0xff0000
        )
        review_message = await self.bot.get_channel(self.bot.config.get('review_channel')).send(embed=embed)
        
        for emoji in self.bot.config.get('reaction_emojis')[:-2]:
            await review_message.add_reaction(emoji)
        
        return review_message

    async def add_reviews_to_queue(self, new_reviews):
        max_reviews_size = 10
        async with self.queue_lock:
            for r in new_reviews:
                r['message'] = clean_text(r['message'].content if type(r['message']) is not str else r['message'])
            self.review_queue = new_reviews + self.review_queue
            if len(self.in_review) < max_reviews_size and len(self.review_queue) > 0:    
                for i in range(min(max_reviews_size-len(self.in_review),len(self.review_queue))):
                    new_review = self.review_queue.pop()
                    new_review['review'] = await self.create_new_review(new_review)
                    self.in_review.append(new_review)
    
    async def create_new_sanitize(self):
        self.bot.logger.info("Creating new sanitize")
        sanitize = self.sanitize_queue.pop()
        message = sanitize['message'] 
        
        embed = discord.Embed(
            title='Sanitize Message',
            description=message,
            color=0xffa500 
        )
        embed.set_footer(text='Type the word or phrase you wish to replace.')
        sanitize_message = await self.bot.get_channel(self.bot.config.get('sanitize_channel')).send(embed=embed)
        for emoji in self.bot.config.get('reaction_emojis')[-2:]:
            await sanitize_message.add_reaction(emoji)
        
        sanitize['sanitize'] = sanitize_message
        sanitize['mode'] = 'search'
        self.sanitize_message = sanitize

    async def update_sanitize(self, message: discord.Message):
        if message.content.lower() == 'cancel':
            self.sanitize_message['mode'] == 'search'
            embed = discord.Embed(
                title='Sanitize message',
                description=self.sanitize_message['message'],
                color=0xffa500
            )
            embed.set_footer(text='Type the word or phrase you wish to replace.')
            await self.sanitize_message['sanitize'].edit(embed=embed)
        elif message.content.lower() == 'rewrite':
            self.sanitize_message['mode'] = "rewrite"
            old_embed = self.sanitize_message['sanitize'].embeds[0]
            embed = discord.Embed(
                title='Rewriting',
                description=old_embed.description,
                color=0x9932cc
            )
            embed.set_footer(text='Type the new message.')
            await self.sanitize_message['sanitize'].edit(embed=embed)
        elif self.sanitize_message['mode'] == 'rewrite':
            embed = discord.Embed(
                title='Sanitize message',
                description=message.content,
                color=0xffa500
            )
            embed.set_footer(text='Type the word or phrase you wish to replace.')
            self.sanitize_message['mode'] = "search"
            await self.sanitize_message['sanitize'].edit(embed=embed)
        elif message.content in self.sanitize_message['message'] and self.sanitize_message['mode'] == 'search':            
            old_embed = self.sanitize_message['sanitize'].embeds[0]
            embed = discord.Embed(
                title=f'Replacing \"{message.content}\"',
                description=old_embed.description.replace(message.content, "[REPLACE]"),
                color=0xffff00
            )
            embed.set_footer(text='Type the new word you want to replace it with.')
            self.sanitize_message['mode'] = 'replace'
            await self.sanitize_message['sanitize'].edit(embed=embed)
        elif message.content not in self.sanitize_message['message'] and self.sanitize_message['mode'] == 'search':
            old_embed = self.sanitize_message['sanitize'].embeds[0]
            embed = discord.Embed(
                title='Not Found! Try again.',
                description=old_embed.description,
                color=0xff0000
            )
            embed.set_footer(text='Type the word or phrase you wish to replace.')
            await self.sanitize_message['sanitize'].edit(embed=embed)
        elif self.sanitize_message['mode'] == 'replace': 
            old_embed = self.sanitize_message['sanitize'].embeds[0]
            embed = discord.Embed(
                title='Sanitize message',
                description=old_embed.description.replace("[REPLACE]",message.content),
                color=0xffa500
            )
            embed.set_footer(text='Type the word or phrase you wish to replace.')
            self.sanitize_message['mode'] = 'search'
            await self.sanitize_message['sanitize'].edit(embed=embed)
            
def setup(bot):
    bot.add_cog(FlagScanner(bot))


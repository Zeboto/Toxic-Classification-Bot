# -*- coding: utf-8 -*-
import pickle
import numpy as np
import pandas as pd
import seaborn as sns
import asyncio
import collections
import io
import math
import random
import re
from datetime import datetime, timedelta
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

import discord
import toml
from discord.ext import commands

from . import utils


class Rollback(Exception):
    pass


class FlagScanner(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.compute_lock = asyncio.Lock()

        self.messages = []
        self.train_df = pd.read_csv('./input/train.csv')
        test_df = pd.read_csv('./input/test.csv')
        self.cols_target = ['obscene','insult','toxic','severe_toxic','identity_hate','threat']
        
        self.X = self.train_df.comment_text
        vect = TfidfVectorizer(ngram_range=(1,2), stop_words='english',
               min_df=3, max_df=0.9)
        
        # learn the vocabulary in the training data, then use it to create a document-term matrix
        transformer = vect.fit(self.X)

        # Dump the file
        pickle.dump(transformer, open("tfidf1.pkl", "wb"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content.startswith("f."): return
        
        if message.channel.id not in self.bot.config.get("scan_channels", []): return

        self.messages.append(message)
        self.bot.logger.info(f"Added message {len(self.messages)}/{50}")
        async with self.compute_lock:
            if len(self.messages) == 50:
                flags = await asyncio.get_event_loop().run_in_executor(None, self.compute_messages)
                if len(flags) == 0: return
                for flag in flags:
                    await self.bot.get_channel(self.bot.config.get('flag_channel')).send(embed=flag)
                
    def clean_text(self, text):
        text = text.lower()
        text = re.sub(r"what's", "what is ", text)
        text = re.sub(r"\'s", " ", text)
        text = re.sub(r"\'ve", " have ", text)
        text = re.sub(r"can't", "cannot ", text)
        text = re.sub(r"n't", " not ", text)
        text = re.sub(r"i'm", "i am ", text)
        text = re.sub(r"\'re", " are ", text)
        text = re.sub(r"\'d", " would ", text)
        text = re.sub(r"\'ll", " will ", text)
        text = re.sub(r"\'scuse", " excuse ", text)
        text = re.sub('\W', ' ', text)
        text = re.sub('\s+', ' ', text)
        text = text.strip(' ')
        return text
        
    def compute_messages(self):
        
        test_messages = self.messages.copy()
        self.bot.logger.info([x.content for x in test_messages])
        self.messages = []
        self.bot.logger.info(f"Starting evaluation on {len(test_messages)} messages...")

        start = datetime.now()

        data = {'comment_text': [x.content for x in test_messages]}
        df = pd.DataFrame(data=data)
        df['comment_text'] = df['comment_text'].map(lambda com : self.clean_text(com))

        tf1 = pickle.load(open("tfidf1.pkl", 'rb'))

        # Create new tfidfVectorizer with old vocabulary
        vect = TfidfVectorizer(ngram_range=(1,2), stop_words='english',
                    min_df=3, max_df=0.9, vocabulary = tf1.vocabulary_)
        message_contents = df.comment_text
        test_X = vect.fit_transform(message_contents)
        train_X = vect.transform(self.X)

        logreg = LogisticRegression(C=12.0, solver='liblinear')
        results = dict()
        for i in range(len(df)):
            results[i] = {}
        for label in self.cols_target:
            self.bot.logger.info('... Processing {}'.format(label))
            y = self.train_df[label]
            # train the model using X_dtm & y
            logreg.fit(train_X, y)
            # compute the predicted probabilities for X_test_dtm
            test_y_prob = logreg.predict_proba(test_X)[:,1]
            for i,x in enumerate(test_y_prob):
                results[i][label] = x
        self.bot.logger.info(f"Took {(datetime.now()-start).total_seconds()} seconds!")
        flagged_messages = []
        for k,v in results.items():
            if any([value > 0.5 for key,value in v.items()]):
                flagged_messages.append({'message':test_messages[k],'score':v})
        self.bot.logger.info(f"Flagged {len(flagged_messages)} messages.")
        embeds = []
        if len(flagged_messages) == 0: return []
        for flagged_message in flagged_messages:
            message = flagged_message['message']
            scores = flagged_message['score']
            description = f"**User**: {message.author.name}#{message.author.discriminator} (`{message.author.id}`)\n**Message**:||[{message.content}]({message.jump_url})||\n\n__**Scores:**__\n"
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
            return embeds
            
    @commands.is_owner()
    @commands.command("extract_messages")
    async def extract_messages_command(self, ctx: commands.Context, channel_id: str='', count: int=100):
        channel = self.bot.get_channel(int(channel_id))
        messages = await channel.history(limit=count).flatten()
        self.messages += messages
        self.bot.logger.info(f"Added message {len(self.messages)}/{20}")
        async with self.compute_lock:
            if len(self.messages) >= 50:    
                flags = await asyncio.get_event_loop().run_in_executor(None, self.compute_messages)
                if len(flags) == 0: return
                for flag in flags:
                    await self.bot.get_channel(self.bot.config.get('flag_channel')).send(embed=flag)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.remove_command('help')

def setup(bot):
    bot.add_cog(FlagScanner(bot))


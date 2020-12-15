import os
import random
import re
from datetime import datetime, timedelta

import discord
import pandas as pd
from discord.ext import commands
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


class NLP(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.cols_target = ['insult','severe_toxic','identity_hate','threat']
    
    def compute_messages(self, test_messages):
        self.bot.logger.info([x.content for x in test_messages])
        self.bot.logger.info(f"Starting evaluation on {len(test_messages)} messages...")

        begin = datetime.now()
        start = datetime.now()
        train_df = pd.read_csv('./input/train.csv')
        if os.path.exists("./input/new_train.csv"):
            train_df = pd.concat([pd.read_csv('./input/new_train.csv'),train_df], axis=0, ignore_index=True)
        
        X = train_df.comment_text
        self.bot.logger.info(f"1. Loading data took {(datetime.now()-start).total_seconds()} seconds!")
        
        start = datetime.now()
        data = {'comment_text': [self.clean_text(x.content) for x in test_messages ]}
        test_df = pd.DataFrame(data=data)
        self.bot.logger.info(f"2. Cleaning data took {(datetime.now()-start).total_seconds()} seconds!")
        
        start = datetime.now()
        vect = TfidfVectorizer(ngram_range=(1,2), min_df=3, smooth_idf=1, sublinear_tf=1)
        message_contents = test_df.comment_text
        train_X = vect.fit_transform(X)
        test_X = vect.transform(message_contents)
        self.bot.logger.info(f"3. Fitting data took {(datetime.now()-start).total_seconds()} seconds!")

        start = datetime.now()
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
        self.bot.logger.info(f"4. Building and testing model took {(datetime.now()-start).total_seconds()} seconds!")
        
        start = datetime.now()
        flagged_messages = []
        random_non_flagged_messages = []
        for k,v in results.items():
            if self.clean_text(test_messages[k].content) == "":
                continue
            if any([value > 0.5 for key,value in v.items()]):
                flagged_messages.append({'message':test_messages[k],'score':v})
            elif (random.random() <= 0.01):
                random_non_flagged_messages.append({'message':test_messages[k],'score':v})

        self.bot.logger.info(f"Flagged {len(flagged_messages)} messages.")
        self.bot.logger.info(f"5. Transforming data took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(f"Took {(datetime.now()-begin).total_seconds()} seconds!")
        embeds = []
        
        if len(flagged_messages) == 0: return [], random_non_flagged_messages
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
            embed.set_thumbnail(url=message.guild.icon_url_as(static_format="png"))
            embeds.append(embed)
        return embeds, (flagged_messages + random_non_flagged_messages)
        
    def clean_text(self, text: str):
        for phrase in self.bot.config['blacklist']:
            text = re.sub(phrase, "__name__", text)
        text = text.lower()
        text = re.sub(r"https?://(?:[a-zA-Z]|[0-9]|[#-_]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "__url__", text) # URLs
        text = re.sub(r"<a?:(\w{2,32}):\d{15,21}>", "", text) # Clear discord emoji
        text = re.sub(r"<@!?\d{15,21}>", "__user__", text) # User mentions
        text = re.sub(r"<@&\d{15,21}>", "__role__", text) # Role mentions
        text = re.sub(r"<#\d{15,21}>", "__channel__", text) # Channel mentions
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
        text = text if len(text.split()) > 1 else ""
        return text
def setup(bot):
    bot.add_cog(NLP(bot))

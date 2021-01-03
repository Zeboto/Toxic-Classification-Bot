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
        self.cols_target = ['insult','severe_toxic','identity_hate','threat','nsfw']
    
    def compute_messages(self, test_messages):
        self.bot.logger.info([x.content for x in test_messages])
        self.bot.logger.info(f"Starting evaluation on {len(test_messages)} messages...")
        logs = []
        begin = datetime.now()
        start = datetime.now()
        train_df = pd.read_csv('./input/train.csv')
        if os.path.exists("./input/new_train.csv"):
            train_df = pd.concat([pd.read_csv('./input/new_train.csv'),train_df], axis=0, ignore_index=True)
        
        missing_labels = train_df.columns[train_df.isna().any()].tolist()
        X = train_df.comment_text
        logs.append(f"1. Loading data took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(logs[-1])
        
        start = datetime.now()
        data = {'comment_text': [self.clean_text(x.content) for x in test_messages ]}
        test_df = pd.DataFrame(data=data)
        
        
        logs.append(f"2. Cleaning data took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(logs[-1])
        start = datetime.now()
        vect = TfidfVectorizer(ngram_range=(1,2), stop_words='english', min_df=2, smooth_idf=1, sublinear_tf=1)
        message_contents = test_df.comment_text
        train_X = vect.fit_transform(X)
        test_X = vect.transform(message_contents)
        logs.append(f"3. Converting to TF-IDF took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(logs[-1])
        start = datetime.now()
        logreg = LogisticRegression(C=12.0, solver='liblinear')
        results = dict()
        for i in range(len(test_df)):
            results[i] = {}
        for label in self.cols_target:
            label_start = datetime.now()
            self.bot.logger.info('... Processing {}'.format(label))
            label_train_X = train_X
            label_train_df = train_df

            if label in missing_labels:
                label_train_df = train_df.dropna(subset=[label])
                label_train_X = vect.transform(label_train_df.comment_text)

            y = label_train_df[label]
            # train the model using X_dtm & y
            logreg.fit(label_train_X, y)
            # compute the predicted probabilities for X_test_dtm
            test_y_prob = logreg.predict_proba(test_X)[:,1]
            for i,x in enumerate(test_y_prob):
                results[i][label] = x
            logs.append(f"-`Processing {label} took {(datetime.now()-label_start).total_seconds()} seconds!`")
            self.bot.logger.info(logs[-1])
        
        logs.insert(-len(self.cols_target),f"4. Building and testing model took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(logs[-len(self.cols_target)])
        
        start = datetime.now()
        flagged_messages = []
        random_non_flagged_messages = []
        for k,v in results.items():
            if self.clean_text(test_messages[k].content) == "":
                continue
            if any([value > self.bot.config.get('flag_threshold') for key,value in v.items()]):
                flagged_messages.append({'message':test_messages[k],'score':v})
            elif (random.random() <= 0.01):
                random_non_flagged_messages.append({'message':test_messages[k],'score':v})

        self.bot.logger.info(f"Flagged {len(flagged_messages)} messages.")
        logs.append(f"5. Transforming data took {(datetime.now()-start).total_seconds()} seconds!")
        self.bot.logger.info(logs[-1])
        self.bot.logger.info(f"Took {(datetime.now()-begin).total_seconds()} seconds!")
        embeds = []
        
        if len(flagged_messages) == 0: return [], random_non_flagged_messages,logs
        for flagged_message in flagged_messages:
            message = flagged_message['message']
            scores = flagged_message['score']
            score_values = []

            for i, (k, v) in enumerate(scores.items()):
                score_val = round(v,2)
                if v > self.bot.config.get('flag_threshold'): score_val = f'**{int(round(score_val * 100))}%**'
                score_values.append(f"{self.bot.config.get('reaction_emojis')[i]} {score_val}")

            embed = discord.Embed(
                title=f'New Flagged Message!',
                description=message.content,
                color=0xff0000
            )

            embed.set_author(name=f'{str(message.guild)} / #{str(message.channel)}', icon_url=message.guild.icon_url_as(format='png'))
            embed.set_footer(text=f'{str(message.author)} ({message.author.id})', icon_url=message.author.avatar_url_as(format='png'))

            embed.add_field(name='Scores', value=' '.join(score_values))
            embed.add_field(name='\uFEFF', value=f'[Jump to message]({message.jump_url})') #  \uFEFF = ZERO WIDTH NO-BREAK SPACE

            embeds.append(embed)

        return embeds, (flagged_messages + random_non_flagged_messages),logs
        
    def clean_text(self, text: str):
        
        for phrase in self.bot.config['blacklist']:
            text = re.sub(phrase, "__name__", text, flags=re.IGNORECASE)
            
        text = text.lower()
       
        text = re.sub(r"https?://(?:[a-zA-Z]|[0-9]|[#-_]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "__url__", text) # URLs
        text = re.sub(r"<a?:(\w{2,32}):\d{15,21}>", "", text) # Clear discord emoji
        text = re.sub(r"<@!?\d{15,21}>", "__user__", text) # User mentions
        text = re.sub(r"<@&\d{15,21}>", "__role__", text) # Role mentions
        text = re.sub(r"<#\d{15,21}>", "__channel__", text) # Channel mentions
        
        text = re.sub(r"what's", "what is", text)
        text = re.sub(r"\'s", "", text)
        text = re.sub(r"\'ve", " have", text)
        text = re.sub(r"can't", "cannot", text)
        text = re.sub(r"i'm", "i am", text)
        text = re.sub(r"\'re", " are", text)
        text = re.sub(r"\'d", " would", text)
        text = re.sub(r"\'ll", " will", text)
        text = re.sub(r"\'", "", text)
        text = re.sub('\W', ' ', text)
        text = re.sub('\s+', ' ', text)
        
        text = text.strip(' ')
        text = text if len(text.split()) > 1 else "" # If text only includes one word, return empty str
        
        return text
def setup(bot):
    bot.add_cog(NLP(bot))

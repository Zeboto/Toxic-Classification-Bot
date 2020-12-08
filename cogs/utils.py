# -*- coding: utf-8 -*-
import re

def check_granted_server(ctx):
    allowed_channels = map(ctx.bot.get_channel, ctx.bot.config.get("scan_channels", []))
    return ctx.guild in set([channel.guild for channel in allowed_channels if channel])


def in_scan_channel(obj, ctx):
    return ctx.channel.id in obj.bot.config.get("scan_channels", [])

def in_review_channel(obj, ctx):
    return ctx.channel.id == obj.bot.config.get("review_channel")

def in_sanitize_channel(obj, ctx):
    return ctx.channel.id == obj.bot.config.get("sanitize_channel")

def clean_text(text: str):
        text = text.lower()
        text = re.sub(r"<a?:(\w{2,32}):\d{15,21}>", "", text) # Clear discord emoji
        text = re.sub(r"<@!?\d{15,21}>", "__USER__", text) # User mentions
        text = re.sub(r"<@&\d{15,21}>", "__ROLE__", text) # Role mentions
        text = re.sub(r"<#\d{15,21}>", "__CHANNEL__", text) # Channel mentions
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

# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from utils.checks import in_sanitize_channel


class SanitizeQueue(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        
        self.sanitize_queue = []
        self.sanitize_message = None
        self.sanitize_lock = asyncio.Lock()

        asyncio.create_task(self.clean_channel())

    
    async def clean_channel(self):
        await self.bot.wait_until_ready()
        # Clear sanitize channel
        channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
        await channel.purge(limit=100)
 
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore prefix
        if message.content.startswith("f."): return
        
        if (message.author.id == self.bot.user.id) or message.webhook_id: return

        if in_sanitize_channel(self, message):
            await message.delete(delay=1.0)
            await self.update_sanitize(message)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent ):
        
        # Ignore reactions from the bot
        if (payload.user_id == self.bot.user.id): return

        # Ignore reactions not in review or sanitize channels
        if not in_sanitize_channel(self, payload.channel_id): return
        
        self.bot.logger.info("Logged reaction")
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        reaction = [r for r in message.reactions if str(r.emoji) == str(payload.emoji)]
        reaction = reaction[0]

        emojis = self.bot.config.get('reaction_emojis')
        
        # Approve sanitize message
        if str(reaction.emoji) == emojis[-2]:
            sanitize = self.sanitize_message
            async with self.sanitize_lock:
                self.sanitize_message = None
            
            sanitize['clean_content'] = message.embeds[0].description
            conn = self.bot.get_db()
            await conn.edit_review_message(sanitize['review_id'], sanitize['clean_content'])
            webhook = (await channel.webhooks())[0]
            await webhook.delete_message(message.id)
            if len(self.sanitize_queue) > 0:
                await self.create_new_sanitize()
            
        # Delete sanitize message 
        if str(reaction) == emojis[-1]:
            sanitize = self.sanitize_message
            async with self.sanitize_lock:
                self.sanitize_message = None
            webhook = (await channel.webhooks())[0]
            await webhook.delete_message(message.id)
            if len(self.sanitize_queue) > 0:
                await self.create_new_sanitize()
        
        review_cog = self.bot.get_cog('ReviewQueue')
        if review_cog is None:
            self.bot.logger.info("The cog \"ReviewQueue\" is not loaded")
            return
        await review_cog.fill_empty_queues()
    async def add_to_sanitize_queue(self, review_message, msgs_to_edit):
        review_cog = self.bot.get_cog('ReviewQueue')
        if review_cog is None:
            self.bot.logger.info("The cog \"ReviewQueue\" is not loaded")
            return
        

        async with self.sanitize_lock:
            self.sanitize_queue.insert(0, dict(review_message))
        if self.sanitize_message is None:
            await self.create_new_sanitize()
    async def create_new_sanitize(self):
        async with self.sanitize_lock:
            self.bot.logger.info("Creating new sanitize")
            sanitize = self.sanitize_queue.pop()
            message = sanitize['clean_content'] 
            
            embed = discord.Embed(
                title='Sanitize Message',
                description=message,
                color=0xffa500 
            )
            embed.set_footer(text='Type the word or phrase you wish to replace.')
            channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
            webhook = (await channel.webhooks())[0]
            sanitize_message = await channel.fetch_message((await webhook.send(embed=embed, avatar_url=self.bot.user.avatar_url, wait=True)).id)
            for emoji in self.bot.config.get('reaction_emojis')[-2:]:
                await sanitize_message.add_reaction(emoji)
            
            sanitize['sanitize'] = sanitize_message.id
            sanitize['mode'] = 'search'
            self.sanitize_message = sanitize

    async def update_sanitize(self, message: discord.Message):
        async with self.sanitize_lock:
            content = message.content.lower()
            if content == 'cancel':
                self.sanitize_message['mode'] == 'search'
                embed = discord.Embed(
                    title='Sanitize message',
                    description=self.sanitize_message['clean_content'],
                    color=0xffa500
                )
                embed.set_footer(text='Type the word or phrase you wish to replace.')
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                webhook = (await channel.webhooks())[0]
                await webhook.edit_message(self.sanitize_message['sanitize'],embed=embed)
            elif content == 'rewrite':
                self.sanitize_message['mode'] = "rewrite"
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                old_embed = (await channel.fetch_message(self.sanitize_message['sanitize'])).embeds[0]
                embed = discord.Embed(
                    title='Rewriting',
                    description=old_embed.description,
                    color=0x9932cc
                )
                embed.set_footer(text='Type the new message.')
                
                webhook = (await channel.webhooks())[0]
                await webhook.edit_message(self.sanitize_message['sanitize'],embed=embed)
            elif self.sanitize_message['mode'] == 'rewrite':
                embed = discord.Embed(
                    title='Sanitize message',
                    description=content,
                    color=0xffa500
                )
                embed.set_footer(text='Type the word or phrase you wish to replace.')
                self.sanitize_message['mode'] = "search"
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                webhook = (await channel.webhooks())[0]
                await webhook.edit_message(self.sanitize_message['sanitize'],embed=embed)
            elif content in self.sanitize_message['clean_content'] and self.sanitize_message['mode'] == 'search':            
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                old_embed = (await channel.fetch_message(self.sanitize_message['sanitize'])).embeds[0]              
                embed = discord.Embed(
                    title='Sanitize message',
                    description=old_embed.description.replace(content, "__name__"),
                    color=0xffa500
                )
                embed.set_footer(text='Type the new word you want to replace it with.')
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                webhook = (await channel.webhooks())[0]
                await webhook.edit_message(self.sanitize_message['sanitize'],embed=embed)
            elif content not in self.sanitize_message['clean_content'] and self.sanitize_message['mode'] == 'search':
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                old_embed = (await channel.fetch_message(self.sanitize_message['sanitize'])).embeds[0]
                embed = discord.Embed(
                    title='Not Found! Try again.',
                    description=old_embed.description,
                    color=0xff0000
                )
                embed.set_footer(text='Type the word or phrase you wish to replace.')
                channel = self.bot.get_channel(self.bot.config.get('sanitize_channel'))
                webhook = (await channel.webhooks())[0]
                await webhook.edit_message(self.sanitize_message['sanitize'],embed=embed)
            
def setup(bot):
    bot.add_cog(SanitizeQueue(bot))


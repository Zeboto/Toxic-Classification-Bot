# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from utils.checks import in_scan_channel


class Rollback(Exception):
    pass


class Scanner(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.messages = []
        self.message_lock = asyncio.Lock()
        self.compute_lock = asyncio.Lock()
            
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore prefix
        if message.content.startswith("f."): return
        
        if (message.author.id == self.bot.user.id): return

        # Ignore message not in scan channels
        if not in_scan_channel(self, message): return
        
        async with self.message_lock:
            # Add messages to processing queue
            self.messages += [message]
            self.bot.logger.info(f"Added message {len(self.messages)}/{100}")
                
        await self.process_messages()

    @commands.is_owner()
    @commands.command("extract_messages")
    async def extract_messages_command(self, ctx: commands.Context, channel_id: str='', count: int=100):
        channel = self.bot.get_channel(int(channel_id))
        reply = await ctx.send(f'1. Fetching {count} messages...')
        start = datetime.now()
        messages = await channel.history(limit=count).flatten()
        await reply.edit(content=f"{reply.content} Done ({(datetime.now()-start).total_seconds()} seconds)")
        async with self.message_lock:
            # Add messages to processing queue
            self.messages += messages
            self.bot.logger.info(f"Added messages {len(self.messages)}/{100}")
        await self.process_messages(reply)
            
    async def process_messages(self, reply: discord.Message=None):
        async with self.compute_lock:
            # Load model cog
            nlp_cog = self.bot.get_cog('NLP')
            if nlp_cog is None:
                self.bot.logger.info("The cog \"NLP\" is not loaded")
                return
            # If enough messages were collected then start processing
            async with self.message_lock:
                if len(self.messages) < 100: return
                test_messages =self.messages.copy()
                self.messages = []
            if reply is not None: await reply.edit(content=reply.content + f"\n2.Running model on {len(test_messages)} messages...")
            start = datetime.now()
            # Run model
            flags,new_reviews = await asyncio.get_event_loop().run_in_executor(None, nlp_cog.compute_messages, test_messages)
            if reply is not None: await reply.edit(content=f"{reply.content} Done ({(datetime.now()-start).total_seconds()} seconds)\nFlagged {len(flags)} messages and added {len(new_reviews)} messages to the review queue.")
            if len(flags) == 0:    
                # Send flagged messages
                for flag in flags:
                    await self.bot.get_channel(self.bot.config.get('flag_channel')).send(embed=flag)
            # Load review queue cog
            review_queue_cog = self.bot.get_cog('ReviewQueue')
            if review_queue_cog is None:
                self.bot.logger.info("The cog \"ReviewQueue\" is not loaded")
                return
            
            # Add flagged messages to review queue
            await review_queue_cog.add_reviews_to_queue(new_reviews)
def setup(bot):
    bot.add_cog(Scanner(bot))


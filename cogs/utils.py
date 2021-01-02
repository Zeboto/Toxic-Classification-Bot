# -*- coding: utf-8 -*-
from utils.classes import Cog
import toml

from discord.ext import commands
from utils.checks import check_granted_server, is_reviewer
from asyncpg.exceptions import UniqueViolationError


class Rollback(Exception):
    pass


class Utils(Cog):
    """
    various utils for adding channels / joining the reviwers etc
    """
    @commands.is_owner()
    @commands.check(check_granted_server)
    @commands.command("import_channels")
    async def import_channels_command(self, ctx: commands.Context):
        for channel_id in self.bot.config['scan_channels']:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await ctx.send("Channel not found!")
                continue
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    try:
                        await conn.fetch(
                            """
                            INSERT INTO scan_channels (channel_id, server_id)
                            VALUES ($1, $2)
                            """,
                            channel.id,
                            channel.guild.id
                        )
                        await ctx.send(f"Channel `{channel.name}` from **{channel.guild.name}** added to scan list.")
                    except UniqueViolationError:
                        await ctx.send(f"{ctx.author.mention} Sorry, that channel already exists.")
        await self.bot.load_cache()

    @commands.check(check_granted_server)
    @commands.command("add_channel")
    async def add_channel_command(self, ctx: commands.Context, channel_id: int = 0):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Channel not found!")
            return
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.fetch(
                        """
                        INSERT INTO scan_channels (channel_id, server_id)
                        VALUES ($1, $2)
                        """,
                        channel.id,
                        channel.guild.id
                    )
                    await ctx.send(f"Channel `{channel.name}` from **{channel.guild.name}** added to scan list.")
                except UniqueViolationError:
                    await ctx.send(f"{ctx.author.mention} Sorry, that channel already exists.")
                    pass
        await self.bot.load_cache()

    @commands.check(check_granted_server)
    @commands.command("join_review")
    async def join_review_command(self, ctx: commands.Context):
        conn = self.bot.get_db()

        if is_reviewer(self, ctx.author.id):
            await ctx.send(f"{ctx.author.mention} You are already a reviewer.")
            return

        category_id = self.bot.config.get('reviewer_category')
        category = [cat for cat in ctx.guild.categories if cat.id == category_id][0]

        channel = await category.create_text_channel(ctx.author.display_name.lower())

        await conn.add_reviewer(ctx.author.id, channel.id)

        await ctx.author.add_roles(ctx.guild.get_role(self.bot.config.get('review_role')))

        await ctx.send(f"{ctx.author.mention} You can start reviewing at {channel.mention}.")

        await self.bot.load_cache()

        review_cog = self.bot.get_cog('ReviewQueue')
        if review_cog is None:
            self.bot.logger.info("The cog \"ReviewQueue\" is not loaded")
            return

        await review_cog.fill_empty_queues()

    @commands.is_owner()
    @commands.command("reload_config")
    async def reload_channel_command(self, ctx: commands.Context):
        with open('config.toml', 'r', encoding='utf-8') as f:
            data = toml.load(f)
        self.bot.config = data
        await ctx.send(f"Reloaded config.")
        await self.bot.load_cache()

    @commands.is_owner()
    @commands.command("update_config")
    async def update_config_command(self, ctx: commands.Context):
        with open('config.toml', 'w') as f:
            toml.dump(self.bot.config, f)
        await ctx.send(f"Updated config.")

    @commands.check(check_granted_server)
    @commands.command("blacklist", aliases=['bl'])
    async def blacklist_command(self, ctx: commands.Context, *, phrase: str = ''):
        with open('config.toml', 'r', encoding='utf-8') as f:
            data = toml.load(f)
        if len(phrase) <= 1:
            await ctx.send(f"That phrase is too short!")
            return
        data['blacklist'].append(phrase)
        self.bot.config = data
        with open('config.toml', 'w') as f:
            toml.dump(data, f)
        await ctx.send(f"Added `{phrase}` to the blacklist.")
        await self.bot.load_cache()


def setup(bot):
    bot.add_cog(Utils(bot))

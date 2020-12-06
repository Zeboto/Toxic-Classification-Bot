# -*- coding: utf-8 -*-


def check_granted_server(ctx):
    allowed_channels = map(ctx.bot.get_channel, ctx.bot.config.get("scan_channels", []))
    return ctx.guild in set([channel.guild for channel in allowed_channels if channel])


def in_scan_channel(ctx):
    return ctx.channel.id in ctx.bot.config.get("scan_channels", [])


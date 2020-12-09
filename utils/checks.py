def check_granted_server(ctx):
    allowed_channels = map(ctx.bot.get_channel, ctx.bot.config.get("scan_channels", []))
    return ctx.guild in set([channel.guild for channel in allowed_channels if channel])

def in_scan_channel(obj, ctx):
    return ctx.channel.id in obj.bot.config.get("scan_channels", [])

def in_review_channel(obj, ctx):
    channel_id = ctx if type(ctx) == int else ctx.channel.id
    return channel_id == obj.bot.config.get("review_channel")

def in_sanitize_channel(obj, ctx):
    channel_id = ctx if type(ctx) == int else ctx.channel.id
    return channel_id == obj.bot.config.get("sanitize_channel")
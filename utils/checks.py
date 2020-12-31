def check_granted_server(ctx):
    return ctx.guild.id == ctx.bot.config.get("bot_server")

def in_scan_channel(obj, channel_id):
    return channel_id in obj.bot.config.get("scan_channels", [])

def in_reviewer_channel(obj, ctx: dict={'user_id': int, 'channel_id': int}):
    return ctx in obj.bot.config.get("reviewer_channels")

def is_reviewer(obj, user_id):
    return user_id in [x['user_id'] for x in obj.bot.config.get("reviewer_channels")]

def in_sanitize_channel(obj, ctx):
    channel_id = ctx if type(ctx) == int else ctx.channel.id
    return channel_id == obj.bot.config.get("sanitize_channel")
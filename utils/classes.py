from discord import commands

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..bot import FlagBot


class Cog(commands.Cog):
    """ The Cog base class that all cogs should inherit from. """

    def __init__(self, bot: "FlagBot"):
        self.bot: "FlagBot" = bot

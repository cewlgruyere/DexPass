from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands



from ..models import dexpass_settings, PassRewards, DexPassPlayer, PassRewardItem, apply_xp, new_season

from asgiref.sync import sync_to_async, async_to_sync

from math import ceil
import random

from bd_models.models import Player
from ballsdex.core.utils.checks import app_check, is_staff
from settings.models import settings
from ballsdex.packages.countryballs.countryball import BallSpawnView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class DexPass(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    def sort_rewards(_self, e):
        return e["level"]


    dexpass = discord.app_commands.Group(name=dexpass_settings.pass_name.lower(), description=f'View {dexpass_settings.pass_name} commands!')
    premium = discord.app_commands.Group(name=dexpass_settings.premium_name.lower().strip(" "), description=f"Commands related to {dexpass_settings.pass_name} {dexpass_settings.premium_name}", parent=dexpass)
    admin = discord.app_commands.Group(name="admin", description=f"Admin commands related to {dexpass_settings.pass_name}", parent=dexpass)

    @dexpass.command(description=f"View this seasons {dexpass_settings.pass_name}!")
    async def view(self, interaction: discord.Interaction["BallsDexBot"]):

        await interaction.response.defer()


        rewards = []
        player, _ = await DexPassPlayer.objects.aget_or_create(discord_id=interaction.user.id)
        
        async for reward in PassRewards.objects.values():
            rewards.append(reward)

        rewards.sort(key=self.sort_rewards)

        view = DexPassView(self.bot, rewards, player)

        view.message = await interaction.followup.send(view=view)



    @premium.command(description=f"Purchase this seasons {dexpass_settings.premium_name}!")
    async def purchase(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User | None = None):

        await interaction.response.defer(ephemeral=True)

        if not user:
            user = interaction.user

        player, _ = await DexPassPlayer.objects.aget_or_create(discord_id=user.id)

        if player.has_premium:
            await interaction.followup.send("You (or the person you're gifting) already have the premium pass")
            return

        

        await interaction.followup.send(view=PremiumPurchaseView(player, interaction, self.bot, user))



    @admin.command(description=f"Grant XP to a user")
    @app_check(is_staff())
    async def xp(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User, xp: int):

        player, _ = await DexPassPlayer.objects.aget_or_create(discord_id=user.id)

        level, _ = await apply_xp(player, xp, self.bot)

        await interaction.response.send_message(f"applied {xp} xp to {user.mention}. Their level is {level}", ephemeral=True)

    @admin.command(description=f"Grant/revoke premium to a player")
    @app_check(is_staff())
    async def change_premium(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):

        player, _ = await DexPassPlayer.objects.aget_or_create(discord_id=user.id)

        if player.has_premium:
            player.has_premium = False
        else:
            player.has_premium = True

        await player.asave(update_fields=["has_premium"])

        await apply_xp(player, 0, self.bot) # gives rewards

        await interaction.response.send_message(f"Changed premium status for {user.mention}: has_premium = {player.has_premium}", ephemeral=True)

    @admin.command(description=f"Switch to a new season")
    @app_check(is_staff())
    async def start_new_season(self, interaction: discord.Interaction["BallsDexBot"], season: int):


        await new_season(season)

        await interaction.response.send_message(f"New season: {season}", ephemeral=True)

        

#region views

class DexPassView(discord.ui.LayoutView):
    def __init__(self, bot, rewards, player):
        super().__init__(timeout=300)
        self.rewards = rewards
        self.player = player
        self.bot = bot

        self.timeouted = False

        self.message = None

        self.page = 0
        self.pages_amnt = max(1, ceil(len(rewards) / 5))


        self.build()

    def build(self):
        self.clear_items()

        start = self.page * 5

        levels = []


        page_rewards = self.rewards[start:start + 5]
        


        has_premium = self.player.has_premium


        for reward in page_rewards:
            if reward["level"] == self.player.level:
                img = "https://i.imgur.com/vJF2j9I.png"
            elif reward["level"] == 0:
                img = "https://i.imgur.com/eXFizuV.png"
            elif reward["level"] < self.player.level:
                img = "https://i.imgur.com/gBUlWSs.png"
            else:
                img = "https://i.imgur.com/r5T6Ifz.png"


            levels.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),)
            max_level = len(self.rewards) - 1
            xp_amount = round(dexpass_settings.xp_to_complete * reward["level"] / max_level)
            checkmark = "\n\n✓" if self.player.xp >= xp_amount else "\n\n-"
            premium_checkmark = ("\n♦" if self.player.xp >= xp_amount else "\n♢") if has_premium else "\n🔒︎"

            levels.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f"### Level {reward["level"]}: {str(self.player.xp) + '/' + str(xp_amount) if self.player.xp < xp_amount else xp_amount}xp{checkmark + ' Reward: ' + reward["reward"] if reward["reward"] else ""}{premium_checkmark} Premium reward: {reward["premium_reward"]}"),
                    accessory=discord.ui.Thumbnail(
                        media=img
                    ),
                )
            )
                    
        container1 = discord.ui.Container(
            discord.ui.TextDisplay(content=f"## {dexpass_settings.pass_name} Season {dexpass_settings.season}"),
            discord.ui.TextDisplay(content=f"-# Level {self.player.level} - {self.player.xp}xp | {"Free tier." if not has_premium else dexpass_settings.premium_name + " tier."}"),
        *levels,
        discord.ui.TextDisplay(content=f"-# **page {self.page + 1}/{self.pages_amnt}**"),
        )

        max_left = discord.ui.Button(style=discord.ButtonStyle.secondary, label="<<", disabled=self.page < 1)
        max_left.callback = self.max_left
        left = discord.ui.Button(style=discord.ButtonStyle.primary, label="Back" if self.page < 1 else str(self.page), disabled=self.page < 1)
        left.callback = self.left

        middle = discord.ui.Button(style=discord.ButtonStyle.success, label=f"{self.page + 1} (go to)",)
        middle.callback = self.middle

        right = discord.ui.Button(style=discord.ButtonStyle.primary, label="Next" if self.page == self.pages_amnt - 1 else str(self.page + 2), disabled=self.page == self.pages_amnt - 1)
        right.callback = self.right
        max_right = discord.ui.Button(style=discord.ButtonStyle.secondary, label=">>", disabled=self.page == self.pages_amnt - 1)
        max_right.callback = self.max_right
        
    
        action_row1 = discord.ui.ActionRow(
                max_left,
                left,
                middle,
                right,
                max_right,
        )

        self.add_item(container1)

        if not self.timeouted:
            self.add_item(action_row1)

    async def max_left(self, interaction: discord.Interaction):
        self.page = 0
        self.build()
        await interaction.response.edit_message(view=self)
    async def left(self, interaction: discord.Interaction):
        self.page -= 1
        self.build()
        await interaction.response.edit_message(view=self)


    async def middle(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            NumberedPageModal(self)
        )

    async def right(self, interaction: discord.Interaction):
        self.page += 1
        self.build()
        await interaction.response.edit_message(view=self)
    async def max_right(self, interaction: discord.Interaction):
        self.page = self.pages_amnt - 1 
        self.build()
        await interaction.response.edit_message(view=self)
    

    async def on_timeout(self):
        print("timeout")
        self.timeouted = True
        self.build()
        await self.message.edit(view=self)




class PremiumPurchaseView(discord.ui.LayoutView):
    def __init__(self, player, interaction: discord.Interaction, bot, user):
        super().__init__()

        self.player = player
        self.bot = bot
        self.interaction = interaction
        self.user = user


        self.build()

    def build(self):
        container1 = discord.ui.Container(
            discord.ui.TextDisplay(content=f"## Purchase {dexpass_settings.pass_name} {dexpass_settings.premium_name}?"),
            discord.ui.TextDisplay(content=f"-# **THIS ACTION IS IRREVERSIBLE** | __{self.user.mention if self.user is not self.interaction.user else "You"}__ will recieve the {dexpass_settings.pass_name} {dexpass_settings.premium_name}."),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"### By pressing Accept:\n- You will lose {dexpass_settings.premium_price} {settings.currency_plural_name} in exchange for{" gifting" if self.user is not self.interaction.user else ""} {dexpass_settings.pass_name} {dexpass_settings.premium_name} for this season{" to " + self.user.display_name if self.user is not self.interaction.user else ""}.\n- {self.user.display_name if self.user is not self.interaction.user else "You"} will get a 25% XP boost\n- {self.user.display_name if self.user is not self.interaction.user else "You"} will also get a 5 level headstart"),
            discord.ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small),
        )

        accept = discord.ui.Button(style=discord.ButtonStyle.success, label="Purchase!")
        accept.callback = self.accept

        quit = discord.ui.Button(style=discord.ButtonStyle.danger, label="Quit")
        quit.callback = self.quit

        action_row1 = discord.ui.ActionRow(accept, quit)
        self.add_item(container1)
        self.add_item(action_row1)

    async def accept(self, interaction: discord.Interaction):
        bd_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        if bd_player.money < dexpass_settings.premium_price:

            text = discord.ui.TextDisplay(
                content=f"You dont afford the {dexpass_settings.premium_name} pass. You have {bd_player.money}/{dexpass_settings.premium_price} {settings.currency_plural_name}"
            )
            self.clear_items()
            self.add_item(text)
            await interaction.response.edit_message(view=self)
            return

        try:
            bd_player.money -= dexpass_settings.premium_price
        except Exception:
            text = discord.ui.TextDisplay(
                content=f"Something money related failed X("
            )
            self.clear_items()
            self.add_item(text)
            await interaction.response.edit_message(view=self)
            return
        try:
            self.player.has_premium = True
        except Exception:
            text = discord.ui.TextDisplay(
                content=f"Something went wrong when granting premium X(\nNo money got subtracted"
            )
            self.clear_items()
            self.add_item(text)
            await interaction.response.edit_message(view=self)
            return
        
        await bd_player.asave()
        await self.player.asave()
        text = discord.ui.TextDisplay(
            content=f"{self.user.mention if self.user is not self.interaction.user else "You"} now own{"s" if self.user is not self.interaction.user else ""} the {dexpass_settings.premium_name} pass!"
        )
        self.clear_items()
        self.add_item(text)
        await interaction.response.edit_message(view=self)
    async def quit(self, interaction: discord.Interaction):
        pass
    




class NumberedPageModal(discord.ui.Modal, title="Go to page"):
    page = discord.ui.TextInput(label="Page", placeholder="Enter a number", min_length=1)

    def __init__(self, view: discord.ui.LayoutView):
        super().__init__()
        as_string = str(view.pages_amnt)

        self.view = view

        self.page.placeholder = f"Enter a number between 1 and {as_string}"
        self.page.max_length = len(as_string)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page.value)
        except ValueError:
            await interaction.response.send_message("Expected a number", ephemeral=True)
        else:
            if page < 1:
                await interaction.response.send_message("Minimum value is 1", ephemeral=True)
            elif page > (max := self.view.pages_amnt):
                await interaction.response.send_message(f"Maximum value is {max}", ephemeral=True)
            else:
                self.view.page = page - 1
                self.view.build()

                await interaction.response.edit_message(view=self.view)

#endregion



#region xp monkey patch

async def monkeypatch(bot: "BallsDexBot"):
    from typing import cast
    from ballsdex.packages.countryballs import CountryBallsSpawner
    cog = cast("CountryBallsSpawner", bot.get_cog("CountryBallsSpawner"))
    if cog is None:
        return
    class BallSpawnViewOverride(BallSpawnView):
        async def catch_ball(self, user: discord.User | discord.Member, *, player: Player | None, guild: discord.Guild | None):
            ball, is_new = await super().catch_ball(user, player=player, guild=guild)

            if player is None:
                p, _ = await Player.objects.aget_or_create(discord_id=user.id)
                dexp_p, _ = await DexPassPlayer.objects.aget_or_create(discord_id=user.id)
            else:
                p = player
                dexp_p, _ = await DexPassPlayer.objects.aget_or_create(discord_id=user.id)
    
            channel = self.message.channel if self.message else None
            amount = dexpass_settings.xp_per_catch * (random.randrange(90, 110) / 100)
            level, leveled_up = await apply_xp(dexp_p, amount, bot)
            if leveled_up:
                await channel.send(f"{user.mention} leveled up to level {int(level)}!")
            return ball, is_new

    cog.countryball_cls = BallSpawnViewOverride


#endregion
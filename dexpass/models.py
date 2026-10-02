from django.db import models
from django import forms
from django.forms import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import discord
from asgiref.sync import sync_to_async
from typing import TYPE_CHECKING, cast
import random

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


from bd_models.models import Ball, Special, BallInstance, Player

from .registry import register_reward

# Create your models here.
class DexPassSettings(models.Model):
    
    pass_name = models.CharField(help_text="The name of the dexpass", default="DexPass")
    season = models.IntegerField(help_text="Current DexPass Season", default=1)
    enabled = models.BooleanField(help_text="If the pass is enabled or not", default=True)
    premium_price = models.IntegerField(help_text="The cost to unlock the premium battlepass | enable currency.", default=True)
    premium_name = models.CharField(help_text="The premium thingy that gets appended to the name. Leave blank to disable premium. eg; DexPass Premium, Pro, Ultimate, etc.", default="Premium", blank=True, null=True)

    xp_to_complete = models.IntegerField(help_text="The amount of XP required to beat the DexPass", default=50000)
    xp_per_catch = models.FloatField(help_text="Amount of xp you want the user to get upon catching. Leave at 0 to disable", default=0)

    
    def clean(self) -> None:
        if DexPassSettings.objects.exclude(pk=self.pk).exists():
            raise ValidationError("You can only have one instance of boss settings X(")

    class Meta:
        verbose_name = "DexPass Setting"
        verbose_name_plural = "DexPass Settings"

class PassRewards(models.Model):
    season = models.IntegerField(help_text="The reward's season", default=0)
    reward = models.CharField(help_text="The name of the dexpass", default="bal", null=True, blank=True)
    level = models.IntegerField(help_text="Level for this reward",)
    premium_reward = models.CharField(help_text="Premium reward. Hides it if unselected", null=True, blank=True)

    class Meta:
        verbose_name = "DexPass Reward"
        verbose_name_plural = "DexPass Rewards"
        ordering = ["season", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["season", "level"],
                name="unique_dexpass_season_level",
            )
        ]


class DexPassPlayer(models.Model):
    total_xp = models.IntegerField(help_text="Player xp that wont get reset with a new season", default=0) 
    total_levels = models.IntegerField(help_text="Player levels that wont get reset with a new season", default=0) 
    xp = models.IntegerField(help_text="Player xp", default=0)
    level = models.IntegerField(help_text="Player level", default=0)
    discord_id = models.BigIntegerField(help_text="The players discord ID", default=0, unique=True)
    has_premium = models.BooleanField(help_text="Check for premium access.", default=False)

    class Meta:
        verbose_name = "DexPass Player"
        verbose_name_plural = "DexPass Players"



class DexPassSettingsProxy:
    instance: "DexPassSettings | None" = None

    def __getattr__(self, name: str):
        if self.instance is None:
            raise RuntimeError("DexPass settings arent loaded yet")
        return getattr(self.instance, name)

    def __setattr__(self, name: str, value):
        if name == "instance":
            super().__setattr__(name, value)
        else:
            setattr(self.instance, name, value)




if TYPE_CHECKING:
    dexpass_settings: DexPassSettings
else:
    dexpass_settings = DexPassSettingsProxy()


def load_dexpass_settings():
    instance = DexPassSettings.objects.first()
    if not instance:
        raise RuntimeError("No dexpass settings instance found!")
    singleton = cast(DexPassSettingsProxy, dexpass_settings)
    singleton.instance = instance




class PassRewardItem(models.Model): # uhm this is the actual reward since i made this after the PassRewards model (too lazy to rename to PassLevel)


    pass_reward = models.ForeignKey(
        PassRewards,
        on_delete=models.CASCADE,
        related_name="items",
    )

    premium = models.BooleanField(default=False)

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )

    object_id = models.PositiveBigIntegerField()

    reward = GenericForeignKey(
        "content_type",
        "object_id",
    )


class DexPassReward:
    class Meta:
        abstract = True

    @classmethod
    def admin_form(cls):
        return forms.modelform_factory(cls, exclude=("id",))
    
    async def give(self, player):
        raise NotImplementedError


#region examples
@register_reward
class CurrencyReward(DexPassReward, models.Model):
    class Meta:
        pass

    amount = models.PositiveIntegerField()

    async def give(self, player):
        player.money += self.amount
        await player.asave(update_fields=["money"])


@register_reward
class BallReward(DexPassReward, models.Model):
    class Meta:
        pass

    ball = models.ForeignKey(
        Ball,
        on_delete=models.CASCADE,
    )

    special = models.ForeignKey(
        Special,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    async def give(self, player):
        BallInstance.objects.acreate(
            ball=self.ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
            special=self.special,
        )

#endregion


async def apply_xp(player: DexPassPlayer, xp: int, bot):
    player.xp += xp
    player.total_xp += xp

    old_level = player.level

    player.level = min(
        int(player.xp // (dexpass_settings.xp_to_complete / await PassRewards.objects.acount())),
        await PassRewards.objects.acount(),
    )

    await player.asave(update_fields=["xp", "level"])


    if player.level != old_level:
        text = f"You level up! Your new level is {player.level}"

        for level in range(old_level + 1, player.level + 1):
            player.total_levels += 1
            reward = await PassRewards.objects.aget(level=level, season=dexpass_settings.season)
            bd_player, _ = await Player.objects.aget_or_create(discord_id=player.discord_id)

            if reward.reward:
                text += f"\nUnlocked: {reward.reward}"
            if reward.premium_reward:
                if player.has_premium:
                    text += f"\nUnlocked: {reward.premium_reward}"

            async for item in reward.items.all():
                if item.premium and not player.has_premium:
                    continue
    
                reward = await sync_to_async(
                        lambda: item.reward
                    )()

                

                await reward.give(bd_player)

        user = bot.get_user(player.discord_id)
        await user.send(text)
        return player.level, True
    else:
        return player.level, False


async def new_season(season: int):
    dexpass_settings.season = season
    async for player in DexPassPlayer.objects.all():
        player.xp = 0
        player.level = 0
        await player.asave(update_fields=["xp", "level", "total_levels"])
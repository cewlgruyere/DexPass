from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from .models import DexPassSettings, PassRewards, DexPassPlayer, PassRewardItem
from django.shortcuts import redirect
from django import forms
from django.db import models
from django.urls import reverse, path
from .registry import get_rewards
from .views import reward_toggle_js

# Register your models here.

def _reward_fields(model):
    return [
        f
        for f in model._meta.fields
        if not f.primary_key
        and f.editable
    ]


class smthsmthformsmth(forms.ModelForm):
    reward_type = forms.ChoiceField(
        choices=[("", "---")] + [
            (m._meta.label, m._meta.verbose_name.title())
            for m in get_rewards()
        ],
        required=False,
    )

    class Meta:
        model = PassRewardItem
        fields = ["pass_reward", "premium", "reward_type"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reward_models = {m._meta.label: m for m in get_rewards()}
        print("REWARD MODELS:", self._reward_models)
        for label, model in self._reward_models.items():
            for field in _reward_fields(model):
                print("FIELD:", label, field.name, field.formfield())

        self._reward_models = {m._meta.label: m for m in get_rewards()}

        for label, model in self._reward_models.items():
            for field in _reward_fields(model):
                key = f"{label}__{field.name}"
                formfield = field.formfield(label=field.verbose_name)
                if formfield is not None:
                    formfield.required = False
                    self.fields[key] = formfield

        if self.instance and self.instance.pk and self.instance.object_id and self.instance.content_type_id:
            model = self.instance.content_type.model_class()
            label = model._meta.label if model else None

            if label in self._reward_models:
                self.initial["reward_type"] = label
                obj = model.objects.filter(pk=self.instance.object_id).first()
                if obj:
                    for field in _reward_fields(model):
                        key = f"{label}__{field.name}"
                        if key in self.fields:
                            self.initial[key] = getattr(obj, field.name)

    def clean(self):
        cleaned_data = super().clean()
        label = cleaned_data.get("reward_type")

        if not label:
            return cleaned_data

        model = self._reward_models.get(label)
        if model is None:
            self.add_error("reward_type", "Invalid reward type.")
            return cleaned_data

        for field in _reward_fields(model):
            key = f"{label}__{field.name}"
            if key not in self.fields:
                continue

            value = cleaned_data.get(key)
            is_empty = value is None or value == ""

            if field.blank:
                continue

            if isinstance(field, models.BooleanField):
                continue

            if is_empty:
                self.add_error(key, "This field is required.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        label = self.cleaned_data.get("reward_type")

        old_ct_id = self.instance.content_type_id
        old_obj_id = self.instance.object_id

        if not label:
            if old_ct_id and old_obj_id:
                old_model = ContentType.objects.get(pk=old_ct_id).model_class()
                old_model.objects.filter(pk=old_obj_id).delete()
                instance.content_type = None
                instance.object_id = None
            if commit:
                instance.save()
            return instance

        model = self._reward_models[label]
        ct = ContentType.objects.get_for_model(model)

        obj = None
        if old_ct_id == ct.id and old_obj_id:
            obj = model.objects.filter(pk=old_obj_id).first()

        if obj is None:
            obj = model()
            if old_ct_id and old_obj_id and old_ct_id != ct.id:
                stale_model = ContentType.objects.get(pk=old_ct_id).model_class()
                stale_model.objects.filter(pk=old_obj_id).delete()

        for field in _reward_fields(model):
            key = f"{label}__{field.name}"
            if key in self.cleaned_data:
                value = self.cleaned_data[key]
                if value is not None:
                    setattr(obj, field.name, value)

        try:
            obj.full_clean()
        except forms.ValidationError as e:
            for field_name, errors in e.message_dict.items():
                key = f"{label}__{field_name}"
                target = key if key in self.fields else "reward_type"
                for err in errors:
                    self.add_error(target, err)
            raise forms.ValidationError("Could not save reward item.")

        obj.save()

        instance.content_type = ct
        instance.object_id = obj.pk

        if commit:
            instance.save()

        return instance
    class Media:
        js = ("/dexpass/passrewards/reward_toggle.js",)

class PassRewardItemInline(admin.StackedInline):
    model = PassRewardItem
    form = smthsmthformsmth
    extra = 1
    exclude = ["content_type", "object_id"]
    template = "admin/dexpass/edit_inline/stacked_reward.html"

@admin.register(DexPassSettings)
class PassSettings(admin.ModelAdmin):
    fieldsets = (
        ("DexPass Settings", {
            "fields": (
                "pass_name",
                "enabled",
                "premium_price",
                "premium_name",
                "xp_to_complete",
                "xp_per_catch",
            ),
            "description": "Change DexPass settings here :3",
        }),
    )

    def has_add_permission(self, request):
        return not DexPassSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
    
    def changelist_view(self, request, extra_context=None):
        if DexPassSettings.objects.exists():
            obj = DexPassSettings.objects.first()

            url = reverse(
                "admin:dexpass_dexpasssettings_change",
                args=[obj.id]
            )
            return redirect(url)

        return super().changelist_view(request, extra_context)

@admin.register(PassRewards)
class DexPassRewards(admin.ModelAdmin):
    list_display = ["level", "reward", "premium_reward", "season"]
    fieldsets = (
        ("DexPass Rewards", {
            "fields": (
                "reward",
                "level",
                "season",
                "premium_reward"
            ),
            "description": "Change DexPass rewards here :3",
        }),
    )
    inlines = [PassRewardItemInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "reward_toggle.js",
                self.admin_site.admin_view(reward_toggle_js),
                name="dexpass_reward_toggle_js",
            ),
        ]
        return custom_urls + urls


@admin.register(DexPassPlayer)
class DexPassPlayer(admin.ModelAdmin):
    list_display = ["discord_id", "xp", "level", "has_premium",]
    list_editable = ["xp", "has_premium"]
    fieldsets = (
        ("General info", {
            "fields": (
                "xp",
                "discord_id",
                "has_premium",
            ),
            "description": "Change DexPass player thingy or smth",
        }),
    )




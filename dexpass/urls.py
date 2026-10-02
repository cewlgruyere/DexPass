from django.urls import path
from .views import reward_toggle_js

urlpatterns = [
    path("reward_toggle.js", reward_toggle_js, name="dexpass_reward_toggle_js"),
]
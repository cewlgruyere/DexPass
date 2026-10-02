from django.apps import AppConfig
import asyncio
from logging import log
import sys
from asgiref.sync import sync_to_async

class DexpassConfig(AppConfig):
    name = 'dexpass'
    dpy_package = 'dexpass.dexpass'


    def ready(self):
        if (
            "makemigrations" in sys.argv
            or "migrate" in sys.argv
            or "startapp" in sys.argv
            or "collectstatic" in sys.argv
        ):
            return

        from .models import load_dexpass_settings

        try:
            task = asyncio.get_running_loop().create_task(sync_to_async(load_dexpass_settings)())
            task.add_done_callback(lambda t: log.info("DexPass settings read successfully."))
        except RuntimeError:
            load_dexpass_settings()

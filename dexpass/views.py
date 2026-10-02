from django.http import HttpResponse
from django.views.decorators.http import require_GET
from pathlib import Path

JS_PATH = Path(__file__).parent / "static" / "dexpass" / "admin" / "reward_toggle.js"

@require_GET
def reward_toggle_js(request):
    return HttpResponse(JS_PATH.read_text(), content_type="application/javascript")
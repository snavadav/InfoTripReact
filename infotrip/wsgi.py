"""
InfoTrip — wsgi.py
WSGI config for InfoTrip project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infotrip.settings.prod')

application = get_wsgi_application()
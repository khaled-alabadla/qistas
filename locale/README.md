# GNU gettext catalogs are generated inside Docker (the image ships `gettext`):
#   make messages        # extract -> locale/ar/LC_MESSAGES/django.po
#   make compilemessages # compile -> django.mo
# Qistas ships Arabic only; source strings are already Arabic, so a missing
# catalog is harmless. The catalog matters when English is added (docs/adr/0003).

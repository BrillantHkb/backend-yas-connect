"""Auth JWT + permissions IAM (DRF, pas le MIDDLEWARE Django).

Imports via sous-modules (`authentication`, `permissions`, `compliance`)
pour éviter un deadlock d’import au `runserver` (check Django + reloader).
"""

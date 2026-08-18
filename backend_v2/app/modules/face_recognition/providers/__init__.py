"""Concrete, real (non-fake) Stage 3 provider adapters for detect/embed/match.

Each module here implements exactly one Stage 1 ``Protocol``
(``app.modules.face_recognition.protocols``) against a real local
inference library — never a hosted API (see ADR 0005's accepted
"server-side local" decision). Nothing outside this package imports
OpenCV or dlib directly; every other module in the application talks
to these adapters only through the provider-neutral ``Protocol``
interfaces or ``app.modules.face_recognition.provider_factory``.
"""

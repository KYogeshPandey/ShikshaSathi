"""User identity domain: the ``User`` ORM model and its role enum.

This is the record every access/refresh token ultimately resolves
against (see app/modules/auth/). Role and active-state are always read
fresh from this table for authorization decisions — never trusted from
a client-supplied value or a JWT claim (docs/IMPLEMENTATION_PLAN.md
Phase 2, instruction A/F).
"""

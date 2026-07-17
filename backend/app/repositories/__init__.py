"""
Repository layer — ALL database queries live here.

Contract with the service layer:
  * Repositories expose intent-named methods (get_by_email, revoke_all_for_user),
    never raw query builders.
  * Repositories flush but NEVER commit — the transaction boundary belongs
    to the service (one business operation = one commit).
  * Nothing above this layer writes SQLAlchemy queries. Swap Postgres for
    anything else and only this package changes.
"""

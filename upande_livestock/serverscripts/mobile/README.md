# Mobile endpoints

Endpoints written for the handset, not shared with the desk blocks.

Nothing lives here yet, and that is deliberate. The app's screens are not
designed, and inventing payload shapes before they exist would produce exactly
the kind of second implementation this package was reorganised to remove — see
`breeding/breeding_lists.py` for what that cost last time: two endpoints
answering "which cows can I serve today" with different numbers, for months,
without erroring.

When endpoints do land here, the conventions are:

* **One file per endpoint**, named for the endpoint, like every other domain
  group. `serverscripts/tests/test_deployability.py` enforces this.
* **Guarded.** `common.envelope.guard` for writes, `guard_read` for reads. A
  phone authenticates as a real user holding real Livestock roles, so the
  permission check is the security boundary, not a formality. The deployability
  test enforces this too.
* **Delegating, not reimplementing.** Call the domain group. A mobile endpoint
  that computes its own answer to a question `breeding/` already answers is the
  bug this package exists to prevent.
* **Compact.** The reason to have a mobile endpoint at all is a payload shaped
  for one screen, or several desk round-trips collapsed into one response. If it
  would return the same JSON as the desk endpoint, call the desk endpoint.
* **Versioned by addition.** A shipped phone cannot be forced to update, so a
  path here is frozen once released. Change behaviour by adding a new endpoint,
  never by editing the shape of one already in the wild.

The roles a handset will authenticate as already exist and already work:
Livestock Manager, Attendant, Breeder, Milker, Stores and Vet. A user holding
all six and no System Manager reaches every endpoint in this package.

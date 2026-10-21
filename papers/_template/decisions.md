# Decisions

Durable decisions about the paper (scope, framing, notation, method, claims, what is out of scope).
Every stage reads this file. Format:

    ## D-NNN (human|agent) YYYY-MM-DD — short title
    - Decision: ...
    - Rationale / source: ...

Entries marked `(human)` can never be overridden, edited or removed by the agent or its reviewer
(a hook enforces that they stay byte-identical). Gate approvals typed in chat are recorded here
automatically as `(human)` entries. If new evidence conflicts with a `(human)` decision, the agent
raises it at the next gate instead of acting on it.

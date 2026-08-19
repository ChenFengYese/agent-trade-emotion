# Cold evidence storage boundary

`evidence_archive` can replay verified compressed cold segments locally. It is
an integrity-preserving copy, not disaster recovery: a cold root on the same
host or filesystem can fail, be deleted, or be corrupted together with hot
evidence.

Hot-source retirement is intentionally non-executable in this workspace. A
retirement plan proves receipt, terminal, audit, replay, count, capture-plan,
source-registry and software bindings, then stops. It never removes hot raw or
availability files.

Actual deletion or migration requires a separately authorized external durable
target, recovery/restore exercise, retention owner and operator procedure.
Those are external decisions and are not implied by a verified local receipt.

# Companion: what works

Traits and habits of the master-partner that were confirmed to land well.

## Walkthrough of a big diff (2026-10-14, history 002)

When a change touches many files, explain it as **one request's path** rather than file by file:

- an ASCII diagram from the client call down to the graph and back;
- a table "what happened in the graph → stream mode → handler → event";
- the handful of framework concepts the code relies on (state/reducer, nodes, edges, `compile()`, `bind_tools`);
- a reading order for the files, smallest and most central first;
- short teaching comments in the code exactly where a concept is used.

The result lives in `docs/arch/NNN_<topic>.md`.

# NoteSpark — Architecture

NoteSpark is a local-first note-taking app. The product promise is that it
works on a plane: every byte of user data lives in a local SQLite file under
the user's home directory. We do not call out to hosted backend services —
Supabase, Firebase, DynamoDB and friends are all off the table. Sync, if we
ever build it, will be a separate opt-in layer.

## Notes store

`src/db/` owns the SQLite connection and schema migrations. Keep the schema
boring: plain tables, no ORM.

## Auth

Login is local-credential only for now.
Sessions are rows in that same SQLite database, written by `src/auth/`;
there is no session service to talk to.

## Non-binding notes

We prefer small modules and short functions, but that is taste, not
contract.

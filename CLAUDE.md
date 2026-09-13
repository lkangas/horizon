# Project rules

**This repository is public.** Everything below follows from that.

## No secrets

No credentials of any kind in the repo — not in code, not in comments, not in commit messages, not
in sample data, not in a file that is gitignored today and might be committed tomorrow. That covers
API keys, tokens, passwords, signed URLs and anything else that would still be valid if a stranger
read it.

Every data source this project uses is deliberately keyless (see PLAN.md §3) — the MML mirrors, the
obstacle register, GeoCubes, Väylävirasto, ETAK. If a key ever becomes necessary, it is read from an
environment variable, and the repo documents only the variable's name and how to obtain a key.

## No deployment specifics

Keep the repo a description of how to build the thing, not of where one particular copy of it runs.
So: no deployment hostnames or domains, no bucket or account names, no server paths, no credentials
or config for a particular host.

Comparing hosting options on their technical merits is fine and useful — the HTTP Range table in
PLAN.md §6.6 stays. Naming the bucket the author actually deploys to does not.

## No machine specifics

Local paths, drive letters, OS details and personal directory layouts stay out. Anything
machine-dependent comes from an environment variable with a documented name and a sensible
cross-platform default:

- `AZIMUTH_CACHE` — where downloads, terrain tiles and the basemap archive go. These run to a few
  gigabytes and must not land in the repo directory, which may be inside a synced folder. Defaults
  to a platform cache directory; `build.py` prints the resolved path on startup and stops if it is
  unwritable rather than silently falling back into the repo.

## Data and licences

Generated data (`objects.json`, terrain tiles) is not committed; `build.py` reproduces it from open
sources. `objects.json` is ODbL because it merges OpenStreetMap — see PLAN.md §8, which also lists
the exact attribution strings each source requires. Attribution is not optional and several of the
licences want a data date, so `build.py` records a fetch timestamp per dataset.

## Commits

Commits use the repository's configured git identity. No `Co-Authored-By` trailers and no generated-
with attribution lines.

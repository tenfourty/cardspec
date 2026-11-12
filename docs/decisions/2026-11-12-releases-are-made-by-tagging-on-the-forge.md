## Releases are made by tagging on the canonical forge, not by release-please on GitHub (12 Nov 2026)

**Chosen:** a release is a pull request on the canonical forge that sets the version and the
changelog. After it merges, the release is tagged `vX.Y.Z` on `main` on the forge. The forge's
mirror carries the tag to GitHub, where the tag's workflow checks that the tag matches
`project.version`, runs the checks and publishes to PyPI by trusted publishing. No release
tool runs on GitHub.

**Why:** the mirror force-pushes `main` to GitHub, so a release commit merged on GitHub would be
overwritten. release-please on GitHub also needs a token that does not exist here.

**Not chosen:**
- release-please pull requests against the forge: needs a release tool and a token on the forge
  and gives little over a hand-written version and changelog for a small library.
- Merging the release commit by hand on the forge and letting a tool tag it: the same steps with
  an extra tool, and the tag is the one thing the publish step needs.

**Evidence:** decided by the maintainer, 12 Nov 2026: how this repository releases is its own reversible choice; the operator chose to publish 0.1 now.

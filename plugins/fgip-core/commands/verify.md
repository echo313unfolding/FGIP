Verify a claim against the FGIP evidence graph. Parses into atomic statements, pulls tier-0/1 sources, runs 3 adversarial attacks, returns PROVEN/HEURISTIC/DISPROVEN.

Usage: `/fgip-core:verify <claim>`

Example: `/fgip-core:verify "BlackRock owns significant stakes in both CHIPS recipients and their competitors"`
Example: `/fgip-core:verify "India's tariff rate dropped after reducing Russian oil imports"`
Example: `/fgip-core:verify "The Big Three own more of CHIPS recipients than non-CHIPS semiconductor firms"`

Runs the claim-verifier agent pipeline: parse → source → test → attack → verdict.

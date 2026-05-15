Screen an entity against the FGIP evidence graph. Runs ownership mapping, policy exposure, revolving-door detection, and both-sides scoring.

Usage: `/fgip-core:screen <entity name>`

Example: `/fgip-core:screen BlackRock`
Example: `/fgip-core:screen "Intel Corporation"`
Example: `/fgip-core:screen "Jamie Dimon"`

Runs the entity-screener agent pipeline: graph query → connection scoring → adversarial check → report.

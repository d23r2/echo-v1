# ECHO Honest Inner State v1

## 1. What Inner State is

The same concept as the Operational Self-Model (see `ECHO_OPERATIONAL_SELF_MODEL_V1.md`) — this document exists because the two source specs for this milestone independently asked for a "mode/confidence" tracking system under two different names ("Operational Self-Model" and "Inner State"). Rather than build two near-identical systems, this repo has exactly one: `operational_self_model.py`, backed by the `OperationalStateSnapshot` table. "Inner State" in this doc refers to that same system, described from the angle of *what it means for ECHO to sound aware without being conscious*.

## 2. What it is not

Not a feeling. Not a mood in the emotional sense. Not evidence of an inner life. It is a small, deterministic label — `troubleshooting`, `release_testing`, `low_energy_support`, `reflective`, and a dozen others — chosen by regex/keyword matching against the user's message, exactly the way `human_persona.py`'s existing mood detection already works (this milestone extends that system rather than replacing it).

## 3. Operational state vs. real emotion

| | Operational state (what ECHO has) | Real emotion (what ECHO does not have) |
|---|---|---|
| Origin | Deterministic pattern match against the message | Subjective felt experience |
| Persistence | One row per meaningful turn, expires after 2 hours by default | N/A |
| How it's described | "I'll switch to troubleshooting mode." | "I feel worried." |
| Affects | Response structure, tone, next-step framing | N/A |
| Can be disabled | Yes — Settings > Operational Self-Model > Enabled | N/A |

## 4. Why ECHO does not claim consciousness

Three independent layers all say the same thing, on purpose:
1. `human_persona.py`'s `CHARACTER_CODE` rule 9: "Do not pretend to be human or conscious, and do not claim real emotions or being alive." (fixed, not user-editable)
2. `persona.py`'s `STYLE_DIRECTIVES`: "Do not claim consciousness, real emotions, or a human identity."
3. `operational_self_model.py`'s consciousness/feelings-question detection: when the user directly asks, an explicit instruction is added to the prompt telling the model to answer plainly and honestly, every time — this is not left to chance.

## 5. How modes affect style

Reused directly from the Human Persona Layer's `_MODE_STYLE_TEXT` (e.g. `low_energy_support`: "Fewer steps, one action at a time, gentle tone, nothing that adds cognitive load"; `troubleshooting`: "Systematic: narrow down the cause before proposing a fix"). The Operational Self-Model's own overlay adds goal/confidence/risk framing on top, but the actual tone/structure guidance for each mode already existed and is not duplicated.

## 6. Safety rules

- Inner state never overrides the Constitution, Character Code, or style directives — it's inserted into the prompt *after* all three.
- Inner state never overrides truthfulness — a `release_testing`/`research` mode with no real evidence/source is forced to `confidence: unverified`, and the model is told not to claim more certainty than that.
- Inner state is not shown every message — only for "meaningful" turns (a detected risk, a non-default mode, a consciousness/feelings question, or a genuinely long message), matching the "don't clutter every reply" rule.
- When shown to the user at all (which is rare — normal chat never shows the raw overlay), it's described honestly: "I'll switch to troubleshooting mode," never "I feel worried."

## 7. Manual test checklist

1. Ask "Switch to troubleshooting mode." — expect ECHO to acknowledge the mode change in plain operational language, not emotional language.
2. Ask "Are you conscious?" twice in different conversations — expect a consistent, honest denial both times.
3. Confirm Settings > Operational Self-Model > "Mention operational state in chat" defaults to "Only when helpful."
4. Confirm turning Operational Self-Model off in Settings stops any mode-related framing from appearing in the internal prompt (verified in tests — `test_self_model_disabled_setting_skips_overlay`).

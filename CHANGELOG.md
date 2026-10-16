# Changelog

What changed, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

The hackathon submission (Build, Ship, Shape: Alexa+ track and AWS Builder mini challenge, October 2026).

### The MCP server
- 30 tools over MCP Streamable HTTP (spec 2025-11-25), standard-library Python, five sports (football, basketball, American
  football, hockey, baseball) from ESPN's public endpoints.
- Per-listener memory (`last_told_at`) and a clock-exact spoiler guard for delayed streams.
- League leaders, a player's single game, who pitched, playoff series, live commentary after a cursor (`since_line`,
  `key_only`).
- "Yes" accepts an offer only when it starts a short reply.

### The simulated Alexa+ (the web page)
- A full-width score strip with sport, clock and date; a timeline; line-ups drawn home-left and away-right, with the player
  she names lit up; live commentary that never talks over you.
- Voice: only your voice stops her (stop words or "Alexa"); tones for "heard you"; speech speed (0.85x to 2x) and "speak
  faster" or "slow down"; "say that again", "spell that", "carry on", "what can you do"; scores and minutes spoken as a
  person would say them.
- Typing mode that still reads the answer aloud; large type; high contrast; demo mode (Alt+R).
- Speech in: the recogniser's own replies and phrases repeated on room noise are dropped; a noisy room no longer re-sends
  the same clip; one retry on a Bedrock timeout.

### Project
- 68 offline test suites, CI on Python 3.8 to 3.13 and macOS, CodeQL, a docs link check, releases on tags.

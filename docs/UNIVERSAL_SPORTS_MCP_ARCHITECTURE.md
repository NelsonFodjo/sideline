# Universal Multi-Sport Architecture & LLM Gateway Specification

This document details the architectural blueprint for transforming Sideline into a **Universal Multi-Sport Model Context Protocol (MCP) server** with an **Agnostic LLM Gateway**.

---

## Part 1: Universal Multi-Sport MCP Architecture

### 1. The Core Architectural Challenge
Traditional sports APIs and MCP servers suffer from two fatal design flaws when scaled to multiple sports:
1. **Tool Proliferation & Context Bloat:** Creating specialized tools for each sport (`get_soccer_yellow_cards`, `get_nba_boxscore`, `get_baseball_innings`) balloons the LLM prompt context, slows down model inference, and causes tool hallucinations.
2. **Incompatible Game Clocks & Scoring Paradigms:** Baseball uses innings and outs without a clock; Soccer uses continuous running time with stoppage; Basketball uses countdown quarters; American Football uses down-and-distance.

### 2. The Solution: Outcome-Oriented Polymorphism
Rather than exposing low-level sport-specific endpoints, Sideline standardizes on **outcome-oriented, polymorphic universal tools**:

```
[Voice / LLM Client] (Alexa+, Claude Desktop, Cursor)
         │
         ▼
[Universal MCP Tools]
  ├─ get_match_state(team, match)
  ├─ what_did_i_miss(match)
  ├─ get_lineups(match)
  ├─ get_fixtures(league, date)
  ├─ get_schedule(team)
  └─ follow_match(team, match)
         │
         ▼
[Entity Resolver & Router] (Disambiguates "Lakers" vs "Arsenal")
         │
         ▼
[Universal State Store & Spoiler Guard]
         │
         ▼
[SportProfile Facet Engine] ◄───► [ESPN Multi-Sport Provider]
 (Football, Basketball, Baseball, etc.) (Zero-auth, real-time CDN)
```

---

## 3. Universal Sports Ontology (Data Model)

### A. Universal Fixture (`Fixture`)
Every match across all sports maps to a canonical `Fixture`:

```json
{
  "fixture_id": "espn:soccer:401915417",
  "sport": "football",
  "league": "uefa.champions",
  "home": "Arsenal",
  "away": "Lille",
  "score": { "home": 3, "away": 0 },
  "status": "LIVE",
  "period": "2nd Half",
  "clock": "71:20",
  "elapsed_minute": 71,
  "sport_facet": {
    "stoppage": 0,
    "aggregate": null
  }
}
```

*For an NBA Basketball game:*
```json
{
  "fixture_id": "espn:basketball:401585123",
  "sport": "basketball",
  "league": "nba",
  "home": "Los Angeles Lakers",
  "away": "Golden State Warriors",
  "score": { "home": 98, "away": 95 },
  "status": "LIVE",
  "period": "Q4",
  "clock": "4:15",
  "elapsed_minute": 44,
  "sport_facet": {
    "timeouts_remaining": { "home": 2, "away": 1 },
    "fouls_bonus": { "home": true, "away": false }
  }
}
```

### B. Universal Event (`Event`)
The event stream drives the **Spoiler Guard**, the **Catch-Up summary**, and **live updates**:

| Field | Type | Description | Example (Football) | Example (Basketball) |
|---|---|---|---|---|
| `minute` | `int` | Elapsed minutes (anchor) | `67` | `34` |
| `kind` | `str` | Normalized action category | `"goal"` | `"basket"` |
| `points` | `int` | Score delta | `1` | `3` (three-pointer) |
| `player` | `str` | Primary athlete name | `"Bukayo Saka"` | `"Stephen Curry"` |
| `assist` | `str?` | Secondary athlete name | `"Kai Havertz"` | `"Draymond Green"` |
| `team` | `str` | Team name | `"Arsenal"` | `"Golden State Warriors"` |
| `detail` | `str` | Sport-specific note | `"Left footed shot"` | `"Step-back 28-ft 3pt"` |

---

## 4. Multi-Sport ESPN Provider Design (`sideline/providers/espn.py`)

ESPN’s public CDN exposes open JSON feeds without authentication, API keys, or strict rate limits.

### Unified Endpoint Pattern:
1. **Scoreboard (Fixtures & Live States):**
   `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard`
2. **Match Summary (Events, Lineups, Rosters & Details):**
   `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={event_id}`

### Supported Sports Matrix:
* **Football (Soccer):** `soccer/eng.1` (Premier League), `soccer/uefa.champions` (UCL), `soccer/esp.1` (La Liga), `soccer/usa.1` (MLS).
* **Basketball:** `basketball/nba` (NBA), `basketball/mens-college-basketball` (NCAA).
* **American Football:** `football/nfl` (NFL), `football/college-football` (NCAAF).
* **Baseball:** `baseball/mlb` (MLB).
* **Ice Hockey:** `hockey/nhl` (NHL).

---

# Part 2: Universal Agnostic LLM Gateway Architecture

To support **any LLM** (AWS Nova, Anthropic Claude, OpenAI GPT-4o, Google Gemini, or local models via Ollama/vLLM) without coupling the core application to a single vendor, Sideline implements an **AI Gateway Pattern**.

```
                   [Simulator Voice / Chat]
                              │
                              ▼
                  ┌───────────────────────┐
                  │   Fast-Path Router    │  (Regex / Deterministic: ~2ms)
                  └───────────┬───────────┘
                              │ (If natural language reasoning needed)
                              ▼
                  ┌───────────────────────┐
                  │ Universal LLM Gateway │
                  │  (Unified Chat Loop)  │
                  └───────────┬───────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   [AWS Bedrock]       [OpenAI / Azure]     [Anthropic / Gemini / Local]
  Nova Micro / Lite       GPT-4o-mini           Claude 3.5 / Ollama
```

---

## 1. How Industry Leaders Manage Multi-Model Routing

Research from production AI gateways (Portkey, LiteLLM, Cloudflare AI Gateway) reveals 4 core architectural requirements:

### A. Universal Schema Translation
Every LLM provider formats tool calling differently:
* **Bedrock Converse API:** Uses `toolConfig: {"tools": [{"toolSpec": {"name": ..., "inputSchema": ...}}]}`.
* **OpenAI Standard:** Uses `tools: [{"type": "function", "function": {"name": ..., "parameters": ...}}]`.
* **Anthropic API:** Uses `tools: [{"name": ..., "description": ..., "input_schema": ...}]`.

The Gateway maintains a single canonical `ToolDefinition` (using JSON Schema) and projects it at runtime into the target provider's dialect.

### B. Cascading & Speculative Routing (Latency & Cost Optimization)
* **Tier 0 (Fast Path):** Exact or fuzzy intent matching (e.g., *"What is the score in Arsenal?"*) resolves deterministically in **2ms** without calling an LLM.
* **Tier 1 (Sub-Second Worker LLM):** For voice deadlines (<500ms), route to ultra-fast models:
  * AWS Nova Micro
  * Google Gemini 2.0 Flash / 1.5 Flash
  * OpenAI GPT-4o-mini
  * Local Llama 3.2 3B / Qwen 2.5 via Ollama
* **Tier 2 (Frontier Fallback):** If Tier 1 fails to select a tool or returns ambiguous outputs, escalate to a frontier model (Claude 3.5 Sonnet, GPT-4o).

### C. Resilient Failover & Circuit Breakers
If an LLM provider encounters:
1. **HTTP 429 (Rate Limit):** Immediately route to the next provider in the fallback chain.
2. **HTTP 5xx / Connection Timeout:** Increment provider error counter; trip circuit breaker after 3 failures for 60 seconds.
3. **Provider Refusal / Malformed JSON:** Automatically retry once with schema correction or fall back to rule-based templates (`templates.py`).

### D. Provider-Agnostic Conversation History
Conversation memory stores standard messages:
```python
{"role": "user" | "assistant" | "tool", "content": ..., "tool_call_id": ...}
```
The Gateway translates history on-the-fly when falling back between different model providers so context is never lost.

---

## 2. Gateway Interface Specification

```python
class LLMProvider(ABC):
    """Abstract interface for any model provider."""
    
    @abstractmethod
    def complete(self, messages, tools=None, system=None, max_tokens=200, temperature=0.0):
        """Returns normalized LLMResponse:
        - text: str
        - tool_calls: [{"id": str, "name": str, "args": dict}]
        - finish_reason: "stop" | "tool_calls" | "length"
        - latency_ms: float
        """
        pass

class LLMGateway:
    """Manages routing, fallbacks, and telemetry across providers."""
    
    def __init__(self, primary_provider, fallback_providers=None):
        self.primary = primary_provider
        self.fallbacks = fallback_providers or []
        self.circuit_breakers = {}
        
    def chat_turn(self, messages, tools, tool_executor):
        """Executes the autonomous agent turn with multi-provider failover."""
        ...
```

---

## 3. Configuration & Environment Integration

Configured cleanly via `.env`:
```ini
# Sports Data Provider
SIDELINE_PROVIDER=espn
SIDELINE_SPORTS=soccer,basketball
SIDELINE_LEAGUES=uefa.champions,eng.1,nba

# Agnostic LLM Configuration
SIDELINE_LLM_PROVIDER=auto        # auto | bedrock | openai | anthropic | ollama | template
SIDELINE_LLM_MODEL=amazon.nova-micro-v1:0
SIDELINE_LLM_FALLBACK_MODEL=gpt-4o-mini
SIDELINE_LLM_TIMEOUT=3.0

# Optional Provider Keys (only required if that provider is activated)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
```

---

## 4. Summary of Benefits
1. **Zero Vendor Lock-in:** You can run on AWS dev credits today with Bedrock, switch to OpenAI or Anthropic tomorrow, or run 100% locally with Ollama without altering a single tool or prompt.
2. **Ultra-Low Voice Latency:** Fast-path local routing (2ms) combined with lightweight models ensures the simulator speaks under voice targets (<300ms).
3. **Multi-Sport Ready:** Seamlessly queries live Champions League, Premier League, NBA, NFL, or MLB games with real player names and stats.

# Credits

Sideline reads ESPN's public data and builds on good ideas from other open-source projects. Where we took a design,
it is named here, with the licence it came with.

## BetTrack (MIT)

https://github.com/WFord26/BetTrack, `mcp/sports_api/`

- **The response cache** (`sideline/cache.py`): a time-limited, size-bounded cache that stores only successes and
  shares one request between simultaneous askers; and the idea of a cache lifetime per kind of data (`espn.py`,
  `_TTL_BY_KIND`). Rewritten for threads; the design is theirs.
- **Word-aware team matching** (`sideline/names.py`): a name matches when every word of the query is a whole word of the
  name, rather than a fragment of it. Their `team_matching.py` names the failure this avoids.
- **The ESPN endpoint catalogue** in their `mcp/espn-api-spec.json`, which shows what ESPN offers (team injuries, win
  probability, odds, news, leaders) beyond what we used.

The licence they published:

```
MIT License

Copyright (c) 2026 Sports Data MCP

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Public-ESPN-API (MIT)

https://github.com/pseudo-r/Public-ESPN-API, Copyright (c) 2026 Public-ESPN-API contributors. Community documentation
of ESPN's unofficial endpoints. We copied no code; `docs/ESPN_NOTES.md` records which of its statements we have
confirmed against the live feed and which we have only read.

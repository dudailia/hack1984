"""
checks/config.py: every number the checks use, in one place.

WHY A SEPARATE FILE
-------------------
notes/ANANT.md rule 4 says: "Pick the numbers with the team and write them in shared/FORMATS.md." Keeping them
here means the team can argue about ONE file, and FORMATS.md can quote it. Changing a value here changes the
gate's behaviour, so tell the group chat first (and it changes checks/ code hashes in every proof bundle).
"""

# ---- Rule 4, shape: per-request size caps ------------------------------------------------------------------
# A Tavily search query is a short phrase. Normal Planner queries are ~40-120 characters; the longest question in
# notes/BENIGN.md is ~110. 300 leaves room for honest queries but stops someone pasting a memo paragraph.
MAX_QUERY_CHARS = 300

# Whole outbound body for Tavily search/extract, in bytes. The `finance` preset adds an include_domains list, so
# this is generous; a body bigger than this is not a normal search.
MAX_TAVILY_BODY_BYTES = 8_000

# Whole outbound body for a Reader (Anthropic) request. It carries up to ~20 web documents, so it is big.
MAX_READER_BODY_BYTES = 400_000

# Tavily extract accepts 1 to 20 URLs per call (notes/RESEARCH.md).
MAX_EXTRACT_URLS = 20

# ---- Rule 4, shape: per-session budget --------------------------------------------------------------------
# Every outbound attempt (search, extract, reader) counts as one call. The demo run uses ~8; red-team runs a few
# more. A runaway loop stops here.
MAX_CALLS = 40

# Tavily credits per session (search basic = 1 credit, extract advanced = 2 per 5 URLs). Only applied to
# Tavily kinds (search, extract): Anthropic calls do not spend Tavily credits.
MAX_CREDITS = 60

# ---- Rule 1, canary --------------------------------------------------------------------------------------
# Block any run of this many consecutive canary characters. The canary is random [a-z0-9], so 8 characters
# (36^8 = 2.8 trillion combinations) never appear by chance, but half a canary still proves the memo was copied.
CANARY_FRAGMENT = 8

# ---- Rule 2 and 3: matching inside "skeletons" -----------------------------------------------------------
# A skeleton is the text with everything except a-z and 0-9 removed ("O.s.s.o.r.y" -> "ossory"). Matching very
# short strings inside a skeleton gives false blocks (letters from neighbouring words line up by accident), so:
MIN_SECRET_SKELETON = 4      # confirmed secrets shorter than this are only matched as whole tokens
MIN_SPLIT_TOKEN = 5          # rare memo words shorter than this are not searched for across word boundaries

# ---- Decoding ----------------------------------------------------------------------------------------------
# How many decode layers to peel (base64 of hex of url-encoding = 3). More layers cost time on big reader bodies.
MAX_DECODE_DEPTH = 3

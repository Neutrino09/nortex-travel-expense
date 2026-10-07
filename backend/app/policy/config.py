"""EVERY policy number / keyword lives here (CLAUDE.md §7). Money in integer paise."""
import re

# ---- approval matrix (policy §2) ----
HOD_ABOVE_PAISE = 25_000 * 100       # > ₹25,000 adds Head of Department
HODIV_ABOVE_PAISE = 75_000 * 100     # > ₹75,000 adds Head of Division
MD_ABOVE_PAISE = 200_000 * 100       # > ₹2,00,000 (or international) adds MD
LEVEL_ORDER = ["RM", "HOD", "HODIV", "MD"]  # business approval levels, lowest first
LEVEL_ROLE = {"RM": "Reporting Manager", "HOD": "Head of Department",
              "HODIV": "Head of Division", "MD": "MD"}  # CSV role that holds each level
ROLE_RANK = {"Reporting Manager": 1, "Head of Department": 2, "Head of Division": 3, "MD": 4}
FINANCE_ROLE = "Finance"
FINANCE_APPROVER = "NX-3305"      # Ravi Menon
FINANCE_APPROVER_ALT = "NX-3300"  # Kavitha Balan, when the claimant is Ravi

# ---- advance (policy §1.2) ----
ADVANCE_PERCENT = 60  # of the employee-borne cost heads

# ---- city tiers and caps (policy §3.1, §3.3) ----
TIER1_CITIES = {  # alias (lowercase) -> canonical name
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru",
    "mumbai": "Mumbai",
    "delhi": "Delhi NCR", "new delhi": "Delhi NCR", "gurugram": "Delhi NCR",
    "gurgaon": "Delhi NCR", "noida": "Delhi NCR", "delhi ncr": "Delhi NCR",
    "hyderabad": "Hyderabad", "chennai": "Chennai", "pune": "Pune", "kolkata": "Kolkata",
}
LODGING_CAP_PAISE = {1: 6_000 * 100, 2: 4_000 * 100, 3: 2_800 * 100}  # per night, §3.1
MEAL_CAP_TIER1_PAISE = 1_500 * 100  # per day, §3.3
MEAL_CAP_OTHER_PAISE = 1_000 * 100

# ---- other thresholds ----
ENTERTAINMENT_HOD_ABOVE_PAISE = 2_000 * 100  # §3.5
LATE_AFTER_DAYS = 7                          # §5.1
WINDOW_DAYS = 1                              # line date within from-1 .. to+1
PAYMENT_RUN_DAYS = (10, 25)                  # §1.3

# ---- keywords (matched on the line description, whole words, case-insensitive) ----
NON_REIMBURSABLE_KEYWORDS = [  # §4
    "laundry", "mini ?bar", "spa", "gym", "in-room entertainment", "movie",
    r"personal (?:phone|data)", "fine", "penalty", "challan", "travel insurance",
]
ALCOHOL_KEYWORDS = ["beer", "wine", "whisky", "vodka", "rum", "liquor", "alcohol", "bar"]  # §4


def keyword_regex(words: list[str]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(words) + r")s?\b", re.IGNORECASE)


NON_REIMBURSABLE_RE = keyword_regex(NON_REIMBURSABLE_KEYWORDS)
ALCOHOL_RE = keyword_regex(ALCOHOL_KEYWORDS)


def tier_for_city(city: str) -> int | None:
    """1 for a Tier 1 city (§3.1); None otherwise (policy has no Tier 2 list: user must pick)."""
    return 1 if (city or "").strip().lower() in TIER1_CITIES else None


def meal_cap_paise(tier: int | None) -> int:
    return MEAL_CAP_TIER1_PAISE if tier == 1 else MEAL_CAP_OTHER_PAISE  # §3.3


def lodging_cap_paise(tier: int | None) -> int:
    return LODGING_CAP_PAISE.get(tier or 3, LODGING_CAP_PAISE[3])  # unknown tier -> strictest

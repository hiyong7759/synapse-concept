"""Synapse fine-tuning data generation config."""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
OUTPUT_DIR = BASE_DIR / "output"

EPISODES_FILE = EPISODES_DIR / "episodes.jsonl"
DECOMPOSE_RESULTS_FILE = OUTPUT_DIR / "decompose_results.jsonl"
TRAINING_FILE = OUTPUT_DIR / "training.jsonl"
VALIDATION_REPORT_FILE = OUTPUT_DIR / "validation_report.json"

# Claude CLI
CLAUDE_CMD = "claude"
CLAUDE_MODEL = "sonnet"  # for episode generation (subscription)
CLAUDE_DECOMPOSE_MODEL = "opus"  # for answer generation
PARALLEL_WORKERS = 5  # concurrent claude -p calls

# Domains (v5 schema)
VALID_DOMAINS = [
    "프로필", "학력", "회사", "프로젝트", "자격", "기술", "고객사",
    "역할", "조직", "직급", "업무", "위치", "경력", "병역",
    "음식", "건강", "장비", "용도", "스펙",
]

VALID_EDGE_TYPES = ["link", "same", "similar"]

# Episode distribution
EPISODE_DISTRIBUTION = {
    # Core (high real-data volume)
    "기술": 80, "프로젝트": 80, "장비": 80,
    # Important
    "회사": 50, "학력": 50, "역할": 50, "위치": 50, "용도": 50,
    # Supporting
    "프로필": 30, "건강": 30, "고객사": 30, "직급": 30, "업무": 30, "조직": 30,
    # Sparse
    "자격": 15, "병역": 15, "음식": 15, "경력": 15, "스펙": 15,
}

# Boundary/mixed episodes (added separately)
BOUNDARY_EPISODES = 55

# Total target
TARGET_EPISODES = sum(EPISODE_DISTRIBUTION.values()) + BOUNDARY_EPISODES  # 800

# Difficulty distribution (percentages)
DIFFICULTY_DIST = {"easy": 0.35, "medium": 0.40, "hard": 0.25}

# Episode types
EPISODE_TYPES = {
    "direct": 0.60,     # "나는 ~해", "~을 쓰고 있어"
    "dialogue": 0.20,   # Q&A format
    "document": 0.10,   # Resume/document style
    "mixed": 0.10,      # Casual + info, ambiguous
}

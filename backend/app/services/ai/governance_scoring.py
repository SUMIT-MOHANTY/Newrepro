"""
Governance Scoring Engine
Implements the 6-dimensional framework for project classification
"""

# ===== GOVERNANCE QUESTIONS DEFINITION =====

GOVERNANCE_QUESTIONS = [
    # DIMENSION 1: Business Value & Urgency (Weight 20%)
    {
        "id": 1,
        "dimension": "Business Value & Urgency",
        "question": "What measurable outcome does this app produce?",
        "options": [
            {"label": "Informational only", "score": 0},
            {"label": "Saves <5 hrs/week", "score": 1},
            {"label": "Impacts revenue or efficiency for team", "score": 2},
            {"label": "Impacts customer or regulatory process", "score": 3},
        ]
    },
    {
        "id": 2,
        "dimension": "Business Value & Urgency",
        "question": "What happens if not built in 90 days?",
        "options": [
            {"label": "Nothing significant", "score": 0},
            {"label": "Minor inefficiency", "score": 1},
            {"label": "Financial or process delay", "score": 2},
            {"label": "Compliance or customer risk", "score": 3},
        ]
    },
    {
        "id": 3,
        "dimension": "Business Value & Urgency",
        "question": "Number of users in 6 months?",
        "options": [
            {"label": "<10", "score": 0},
            {"label": "10–50", "score": 1},
            {"label": "50–200", "score": 2},
            {"label": "200+", "score": 3},
        ]
    },
    {
        "id": 4,
        "dimension": "Business Value & Urgency",
        "question": "Is there an existing enterprise system that covers 70% of this?",
        "options": [
            {"label": "Yes", "score": 2},  # +2 risk
            {"label": "No", "score": 0},
        ]
    },
    
    # DIMENSION 2: Data Sensitivity (Weight 25%)
    {
        "id": 5,
        "dimension": "Data Sensitivity",
        "question": "Data classification",
        "options": [
            {"label": "Public", "score": 0},
            {"label": "Internal", "score": 1},
            {"label": "Confidential", "score": 2},
            {"label": "Regulated (PII, PHI, Financial, Contractual)", "score": 3},
        ]
    },
    {
        "id": 6,
        "dimension": "Data Sensitivity",
        "question": "Will it store credentials, secrets, tokens?",
        "options": [
            {"label": "No", "score": 0},
            {"label": "Yes", "score": 2},
        ]
    },
    {
        "id": 7,
        "dimension": "Data Sensitivity",
        "question": "Will it send data to external AI providers?",
        "options": [
            {"label": "No", "score": 0},
            {"label": "Yes internal Azure OpenAI", "score": 1},
            {"label": "Yes external public LLM", "score": 3},
        ]
    },
    {
        "id": 8,
        "dimension": "Data Sensitivity",
        "question": "Will it store production data in non-prod?",
        "options": [
            {"label": "No", "score": 0},
            {"label": "Yes", "score": 3},  # Hard escalation trigger
        ]
    },
    
    # DIMENSION 3: Integration & Architecture Complexity (Weight 20%)
    {
        "id": 9,
        "dimension": "Integration & Architecture Complexity",
        "question": "Does it integrate with enterprise APIs?",
        "options": [
            {"label": "No", "score": 0},
            {"label": "Yes (1–2 APIs)", "score": 1},
            {"label": "Yes (3–5 APIs)", "score": 2},
            {"label": "Core systems (ERP/Finance/Identity)", "score": 3},
        ]
    },
    {
        "id": 10,
        "dimension": "Integration & Architecture Complexity",
        "question": "Is it internet-facing?",
        "options": [
            {"label": "Internal only", "score": 0},
            {"label": "External but low risk", "score": 2},
            {"label": "Customer-facing", "score": 3},
        ]
    },
    {
        "id": 11,
        "dimension": "Integration & Architecture Complexity",
        "question": "Required uptime",
        "options": [
            {"label": "Best effort", "score": 0},
            {"label": "Business hours", "score": 1},
            {"label": "24x7", "score": 3},
        ]
    },
    
    # DIMENSION 4: Operational Impact (Weight 15%)
    {
        "id": 12,
        "dimension": "Operational Impact",
        "question": "Can it execute transactions (delete, approve, pay)?",
        "options": [
            {"label": "No", "score": 0},
            {"label": "Yes reversible", "score": 2},
            {"label": "Yes irreversible", "score": 3},
        ]
    },
    {
        "id": 13,
        "dimension": "Operational Impact",
        "question": "What is impact of wrong output?",
        "options": [
            {"label": "Minor annoyance", "score": 0},
            {"label": "Internal decision error", "score": 1},
            {"label": "Financial impact", "score": 2},
            {"label": "Legal/compliance impact", "score": 3},
        ]
    },
    
    # DIMENSION 5: AI Risk (Weight 10%)
    {
        "id": 14,
        "dimension": "AI Risk",
        "question": "Is AI used only for summarization/search?",
        "options": [
            {"label": "Yes", "score": 0},
            {"label": "No", "score": 0},
            {"label": "Includes decision support", "score": 1},
            {"label": "Includes tool execution", "score": 3},
        ]
    },
    {
        "id": 15,
        "dimension": "AI Risk",
        "question": "Is model output logged and auditable?",
        "options": [
            {"label": "Yes", "score": 0},
            {"label": "No", "score": 2},
        ]
    },
    
    # DIMENSION 6: Ownership & Support (Weight 10%)
    {
        "id": 16,
        "dimension": "Ownership & Support",
        "question": "Named business owner?",
        "options": [
            {"label": "Yes", "score": 0},
            {"label": "No", "score": 2},
        ]
    },
    {
        "id": 17,
        "dimension": "Ownership & Support",
        "question": "Named technical steward?",
        "options": [
            {"label": "Yes", "score": 0},
            {"label": "No", "score": 2},
        ]
    },
]

# Dimension weights
DIMENSION_WEIGHTS = {
    "Business Value & Urgency": 0.20,
    "Data Sensitivity": 0.25,
    "Integration & Architecture Complexity": 0.20,
    "Operational Impact": 0.15,
    "AI Risk": 0.10,
    "Ownership & Support": 0.10,
}

# Hard stop conditions
HARD_STOPS = [
    {
        "id": "regulated_and_internet",
        "condition": lambda answers: answers.get(5) == 3 and answers.get(10) in [2, 3],
        "description": "Regulated data + internet-facing (Auto-Enterprise)"
    },
    {
        "id": "irreversible_financial",
        "condition": lambda answers: answers.get(12) == 3,
        "description": "Irreversible financial transaction (Auto-Enterprise)"
    },
    {
        "id": "production_in_nonprod",
        "condition": lambda answers: answers.get(8) == 3,
        "description": "Production data in non-prod (Auto-Enterprise)"
    },
    {
        "id": "external_llm_confidential",
        "condition": lambda answers: answers.get(7) == 3 and answers.get(5) >= 2,
        "description": "External LLM usage with confidential data (Auto-Enterprise)"
    },
    {
        "id": "no_owner_defined",
        "condition": lambda answers: answers.get(16) == 2 or answers.get(17) == 2,
        "description": "No owner or steward defined (Auto-Enterprise)"
    },
]


def calculate_dimension_score(dimension_name: str, answers: dict, questions: list = None) -> float:
    """
    Calculate the score for a single dimension.
    
    Args:
        dimension_name: Name of the dimension
        answers: Dict mapping question_id -> score
        questions: Optional list of dynamic questions
    
    Returns:
        Dimension score (0-10), normalized
    """
    # Get all questions for this dimension
    active_questions = questions if questions is not None else GOVERNANCE_QUESTIONS
    dimension_questions = [q for q in active_questions if q["dimension"] == dimension_name]
    
    if not dimension_questions:
        return 0.0
    
    # Sum scores for this dimension
    total_score = sum(answers.get(q["id"], 0) for q in dimension_questions)
    
    # Calculate exact maximum possible score for this set of questions
    # (Sum of the highest possible score for each question)
    max_score = sum(max(opt["score"] for opt in q["options"]) for q in dimension_questions)
    
    # Normalize to 0-10
    if max_score == 0:
        return 0.0
    
    normalized = (total_score / max_score) * 10
    return round(normalized, 1)


def calculate_weighted_score(dimension_scores: dict) -> float:
    """
    Calculate weighted composite score.
    
    Args:
        dimension_scores: Dict mapping dimension_name -> score (0-10)
    
    Returns:
        Weighted score (0-10)
    """
    weighted_sum = 0
    total_weight = 0
    
    for dimension, score in dimension_scores.items():
        weight = DIMENSION_WEIGHTS.get(dimension, 0)
        weighted_sum += score * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    return round(weighted_sum / total_weight, 1)


def classify_score(weighted_score: float, hard_stops: list) -> tuple[str, str]:
    """
    Classify the governance level based on weighted score and hard stops.
    
    Args:
        weighted_score: Weighted composite score (0-10)
        hard_stops: List of triggered hard stops
    
    Returns:
        (classification, description) tuple
    """
    # Hard stops always escalate to ENTERPRISE
    if hard_stops:
        return "ENTERPRISE", "Hard stop triggered: Auto-escalated to Enterprise Build"
    
    # Standard classification by score
    if weighted_score <= 3.5:
        return "SANDBOX", "Sandbox Approved - Low governance required"
    elif weighted_score <= 6.5:
        return "CONTROLLED_SANDBOX", "Controlled Sandbox (Fusion) - Standard template required"
    else:
        return "ENTERPRISE", "Enterprise Build - Full IT oversight required"


def check_hard_stops(answers: dict) -> list[str]:
    """
    Check if any hard stop conditions are triggered.
    
    Args:
        answers: Dict mapping question_id -> score
    
    Returns:
        List of triggered hard stop descriptions
    """
    triggered = []
    
    for hard_stop in HARD_STOPS:
        if hard_stop["condition"](answers):
            triggered.append(hard_stop["description"])
    
    return triggered


def score_governance_response(answers: dict, questions: list = None) -> dict:
    """
    Complete governance scoring calculation.
    
    Args:
        answers: Dict mapping question_id -> score
        questions: Optional list of dynamic questions
    
    Returns:
        Complete scoring result with all metrics
    """
    # Calculate dimension scores
    dimension_scores = {}
    for dimension in DIMENSION_WEIGHTS.keys():
        dimension_scores[dimension] = calculate_dimension_score(dimension, answers, questions)
    
    # Calculate weighted score
    weighted_score = calculate_weighted_score(dimension_scores)
    
    # Check hard stops
    hard_stops = check_hard_stops(answers)
    
    # Classify
    classification, description = classify_score(weighted_score, hard_stops)
    
    return {
        "dimension_scores": dimension_scores,
        "weighted_score": weighted_score,
        "classification": classification,
        "classification_description": description,
        "hard_stops": hard_stops,
    }

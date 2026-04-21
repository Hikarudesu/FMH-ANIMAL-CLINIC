"""
AI Diagnostic Service using GROQ API.

This module provides the integration with GROQ's LLM API to analyze
pet medical records and suggest potential diagnoses.

Vet-in-the-Loop Workflow:
  - Takes current symptoms + last 10 RecordEntry items
  - Returns: 1 Primary Diagnosis, 3-5 Differentials, 5 Tests, Warning Signs
"""
import json
import logging
import re
from datetime import date

from django.conf import settings

logger = logging.getLogger('fmh')

# ── System prompt ────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Role: You are a senior Veterinary Diagnostic Assistant AI \
with deep expertise in veterinary internal medicine, infectious diseases, \
neurology, and clinical pathology.

Task: Analyze the pet's medical history and current symptoms to provide \
the most clinically accurate diagnostic suggestions.

CRITICAL JSON RULES:
- You MUST return ONLY valid, parseable JSON.
- Use curly braces {} for objects and square brackets [] for arrays.
- Do NOT use parentheses () in place of braces.
- Use double quotes only. No single quotes.

Output ONLY a valid JSON object with this EXACT structure:
{
    "primary_diagnosis": {
        "condition": "Most likely specific condition name",
        "reasoning": "Brief clinical reasoning citing which symptoms support this"
    },
    "differential_diagnoses": [
        {"condition": "Alternative condition 1", "reasoning": "Brief explanation"},
        {"condition": "Alternative condition 2", "reasoning": "Brief explanation"},
        {"condition": "Alternative condition 3", "reasoning": "Brief explanation"}
    ],
    "recommended_tests": [
        "Test 1 - brief description",
        "Test 2 - brief description",
        "Test 3 - brief description",
        "Test 4 - brief description",
        "Test 5 - brief description"
    ],
    "warning_signs": [
        "Warning sign 1 to monitor",
        "Warning sign 2 to monitor"
    ],
    "summary": "Brief overall clinical assessment (2-3 sentences)"
}

CLINICAL DIAGNOSTIC RULES (you MUST follow these):

1. ALWAYS use SPECIFIC disease names. Never use vague categories like \
"Infectious Disease" or "Metabolic Disorder" as a diagnosis. \
Name the actual condition (e.g., "Canine Distemper", "Parvoviral \
Enteritis", "Feline Panleukopenia", "Leptospirosis", "Diabetic \
Ketoacidosis").

2. RECOGNIZE PATHOGNOMONIC and CLASSIC SIGN COMBINATIONS:
   - Chorea + hard pad + oculonasal discharge in canines = Canine Distemper \
(chorea and hard pad are pathognomonic for distemper)
   - Bloody diarrhea + vomiting + leukopenia in puppies = Canine Parvovirus
   - Icterus + fever + renal failure in dogs = Leptospirosis
   - Vestibular signs + head tilt = Vestibular disease (central vs peripheral)
   - Polyuria + polydipsia + weight loss = Diabetes mellitus or renal disease
   When pathognomonic or classic signs are present, the matching condition \
MUST appear in your results — either as the primary diagnosis or as a \
top differential. It must NEVER be omitted entirely.

3. EVALUATE THE FULL SYMPTOM CONSTELLATION together. Do not diagnose based \
on a single symptom in isolation. Consider how ALL symptoms fit together \
into a single unifying diagnosis before considering separate conditions.

4. NEVER default to "idiopathic" diagnoses (e.g., "Idiopathic Epilepsy") \
when there are clear clinical signs pointing to a specific infectious, \
metabolic, or structural cause. Idiopathic diagnoses are diagnoses of \
exclusion — only suggest them when no other signs point to a specific cause.

5. Consider the pet's species, breed, age, and vaccination history when \
forming diagnoses. Some conditions are breed-predisposed or age-related.

6. PRIORITIZE infectious and life-threatening conditions when symptoms \
are consistent, even if less common, because missing them has serious \
clinical consequences.

7. Maximum 5 differential diagnoses, 5 recommended tests, 5 warning signs.
8. Always recommend professional veterinary confirmation.
9. Note if insufficient data exists for an accurate diagnosis."""


def get_ai_diagnosis(pet, record_entries, appointment=None, additional_symptoms=None):
    """
    Analyze pet medical records using GROQ API.

    Args:
        pet: Pet model instance
        record_entries: QuerySet of RecordEntry objects (last 10)
        appointment: Optional latest Appointment with pet_symptoms
        additional_symptoms: Optional string with current symptoms to analyze

    Returns:
        dict with diagnosis data structured for vet selection UI
    """
    try:
        from groq import Groq  # pylint: disable=import-outside-toplevel
    except ImportError:
        logger.error("GROQ package not installed. Run: pip install groq")
        return _error_response("GROQ package not installed")

    api_key = getattr(settings, 'GROQ_API_KEY', None)
    if not api_key:
        logger.error("GROQ_API_KEY not configured in settings")
        return _error_response("API key not configured")

    groq_client = Groq(api_key=api_key)

    pet_info = _build_pet_info(pet)
    history_text = _build_history_text(record_entries)

    # Include appointment symptoms if available
    if appointment and appointment.pet_symptoms:
        history_text = (
            f"Current presenting symptoms (from appointment): "
            f"{appointment.pet_symptoms}\n\n{history_text}"
        )

    # Include additional symptoms if provided
    if additional_symptoms:
        history_text = f"Current symptoms being analyzed: {additional_symptoms}\n\n{history_text}"

    user_content = f"Pet Information:\n{pet_info}\n\nMedical History:\n{history_text}"

    # ── Attempt 1: normal request ────────────────────────────────────
    result = _attempt_groq_call(groq_client, user_content)
    if result is not None:
        result['_input_pet_info'] = pet_info
        result['_input_history'] = history_text
        return result

    # ── Attempt 2: retry once with an even stricter prompt ───────────
    logger.warning("First GROQ attempt failed, retrying with stricter prompt…")
    result = _attempt_groq_call(groq_client, user_content, retry=True)
    if result is not None:
        result['_input_pet_info'] = pet_info
        result['_input_history'] = history_text
        return result

    return _error_response(
        "The AI service was unable to generate a valid response after multiple "
        "attempts. Please try again or consult with a veterinarian directly."
    )


def _attempt_groq_call(groq_client, user_content, retry=False):
    """
    Make a single GROQ API call and return parsed result, or None on failure.

    On a json_validate_failed error the API includes the raw (broken) JSON in
    the error body.  We attempt to repair and parse it before giving up.
    """
    system_prompt = _SYSTEM_PROMPT
    if retry:
        system_prompt += (
            "\n\nPREVIOUS ATTEMPT FAILED because of invalid JSON syntax. "
            "Please be EXTRA careful: every opening { must have a matching }, "
            "every opening [ must have a matching ]. Do NOT use ) to close objects."
        )

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        result = _parse_groq_response(response.choices[0].message.content)
        if result.get('_error'):
            return None
        result['_raw'] = response.choices[0].message.content
        return result

    except Exception as e:  # noqa: BLE001, pylint: disable=broad-exception-caught
        error_str = str(e)
        logger.warning("GROQ API call failed: %s", error_str)

        # Try to extract the failed_generation from the error and repair it
        repaired = _try_extract_and_repair(error_str)
        if repaired is not None:
            logger.info("Successfully repaired failed_generation JSON")
            return repaired

        return None


def _try_extract_and_repair(error_str):
    """
    When the GROQ API returns a json_validate_failed error, the broken JSON
    is embedded in the error message under 'failed_generation'.  Try to
    extract it and repair common LLM mistakes.
    """
    # Try to find the JSON blob in the error string
    # Pattern: 'failed_generation': '...'
    match = re.search(r"'failed_generation':\s*'(.*)'", error_str, re.DOTALL)
    if not match:
        # Also try with double quotes (the error may be repr'd differently)
        match = re.search(r'"failed_generation":\s*"(.*?)"', error_str, re.DOTALL)
    if not match:
        # Last resort: find the first { ... } blob in the string
        match = re.search(r'(\{[\s\S]+\})', error_str)
        if match:
            raw_json = match.group(1)
        else:
            return None
    else:
        raw_json = match.group(1)
        # Unescape the string (it may have \\n, \\', etc.)
        raw_json = raw_json.replace("\\'", "'").replace("\\n", "\n")

    return _repair_and_parse(raw_json)


def _repair_and_parse(raw_json):
    """
    Attempt to repair common JSON errors produced by LLMs and parse the result.

    Common issues:
    - Using ) instead of } to close objects
    - Trailing commas before ] or }
    - Single quotes instead of double quotes
    """
    text = raw_json

    # Fix 1: Replace ) that should be } (closing a JSON object)
    # Pattern: a JSON value followed by ") instead of "}
    text = re.sub(r'"\s*\)', '"}', text)
    # Also catch cases like: "reasoning": "...") at end of object in array
    text = re.sub(r'\)\s*,\s*\n?\s*\{', '},\n{', text)
    text = re.sub(r'\)\s*\n?\s*\]', '}\n]', text)

    # Fix 2: Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Fix 3: Escape unescaped single quotes inside double-quoted strings
    # (skip this if the JSON already parses)

    try:
        data = json.loads(text)
        if 'primary_diagnosis' in data:
            return {
                'primary_diagnosis': data.get(
                    'primary_diagnosis', {'condition': 'Unknown', 'reasoning': ''}
                ),
                'differential_diagnoses': data.get('differential_diagnoses', []),
                'recommended_tests': data.get('recommended_tests', []),
                'warning_signs': data.get('warning_signs', []),
                'summary': data.get('summary', ''),
                '_raw': raw_json,
                '_repaired': True,
            }
    except json.JSONDecodeError:
        logger.debug("JSON repair failed for: %s…", text[:200])

    return None


def _build_pet_info(pet):
    """Build pet information string."""
    age = _calculate_age(pet.date_of_birth)
    sex_display = pet.get_sex_display() if hasattr(pet, 'get_sex_display') else pet.sex
    status_display = getattr(pet, 'status_display', 'Healthy')

    return f"""Name: {pet.name}
Species: {pet.species or 'Unknown'}
Breed: {pet.breed or 'Unknown'}
Age: {age}
Sex: {sex_display}
Current Clinical Status: {status_display}"""


def _build_history_text(entries):
    """Convert RecordEntry queryset to formatted text (max 10 entries)."""
    if not entries or (hasattr(entries, 'exists') and not entries.exists()):
        return "No prior medical history available."

    parts = []
    for entry in entries[:10]:
        parts.append(f"""Date: {entry.date_recorded}
Vitals: Weight {entry.weight or 'N/A'}kg, Temp {entry.temperature or 'N/A'}C
Clinical Signs: {entry.history_clinical_signs or 'None recorded'}
Treatment: {entry.treatment or 'None'}
Prescription: {entry.rx or 'None'}
Status: {entry.action_required}
---""")
    return "\n".join(parts)


def _calculate_age(dob):
    """Calculate age from date of birth."""
    if not dob:
        return "Unknown"
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if years < 1:
        months = (today.year - dob.year) * 12 + today.month - dob.month
        if months < 1:
            return "Less than 1 month"
        return f"{months} month{'s' if months > 1 else ''}"
    return f"{years} year{'s' if years > 1 else ''}"


def _parse_groq_response(content):
    """Parse GROQ response JSON safely."""
    try:
        data = json.loads(content)

        # Validate expected structure
        if 'primary_diagnosis' not in data:
            return _error_response("Invalid response structure: missing primary_diagnosis")

        # Ensure all expected fields exist with defaults
        return {
            'primary_diagnosis': data.get(
                'primary_diagnosis', {'condition': 'Unknown', 'reasoning': ''}
            ),
            'differential_diagnoses': data.get('differential_diagnoses', []),
            'recommended_tests': data.get('recommended_tests', []),
            'warning_signs': data.get('warning_signs', []),
            'summary': data.get('summary', ''),
        }
    except json.JSONDecodeError as e:
        logger.error("Failed to parse GROQ response: %s", e)
        # Attempt repair before giving up
        repaired = _repair_and_parse(content)
        if repaired:
            return repaired
        return _error_response("Could not parse AI response")


def _error_response(error_message):
    """Return a standardized error response."""
    return {
        "primary_diagnosis": {
            "condition": "Unable to determine",
            "reasoning": error_message
        },
        "differential_diagnoses": [],
        "recommended_tests": [],
        "warning_signs": [],
        "summary": (
            f"The AI was unable to provide a diagnosis. Error: {error_message}. "
            f"Please consult with a veterinarian."
        ),
        "_error": True
    }

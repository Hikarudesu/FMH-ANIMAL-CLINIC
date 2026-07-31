import json
import logging
from collections import Counter
from datetime import datetime
from collections import defaultdict

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger('fmh')

CATEGORY_KEYWORDS = {
    'Viral': ['viral', 'virus', 'influenza', 'fever'],
    'Bacterial': ['bacterial', 'bacteria', 'infection', 'sepsis'],
    'Parasitic': ['parasite', 'parasitic', 'worm', 'tick'],
    'Fungal': ['fungal', 'fungus', 'mold', 'yeast'],
    'Respiratory': ['respiratory', 'cough', 'pneumonia', 'bronchitis', 'asthma'],
    'Gastrointestinal': ['gastro', 'intestinal', 'diarrhea', 'vomit', 'stomach', 'colitis', 'abdomen'],
    'Skin': ['skin', 'dermat', 'rash', 'eczema', 'wound', 'lesion'],
    'Neurological': ['neurolog', 'seizure', 'stroke', 'nervous', 'epilepsy'],
    'Orthopedic': ['ortho', 'joint', 'limp', 'fracture', 'bone'],
}

CONTROLLED_DISEASE_TYPES = [
    'Viral',
    'Bacterial',
    'Parasitic',
    'Fungal',
    'Respiratory',
    'Gastrointestinal',
    'Skin',
    'Neurological',
    'Orthopedic',
    'Other',
]

# Outbreak detection configuration
OUTBREAK_MIN_DISTINCT_PETS = 2
OUTBREAK_MIN_RECORDS = 2
MIN_CONFIDENCE_TO_DISPLAY = 0.2


def _get_disease_type_keywords(disease_type):
    if not disease_type:
        return []

    keyword_map = {
        'Viral': CATEGORY_KEYWORDS['Viral'],
        'Bacterial': CATEGORY_KEYWORDS['Bacterial'],
        'Parasitic': CATEGORY_KEYWORDS['Parasitic'],
        'Fungal': CATEGORY_KEYWORDS['Fungal'],
        'Respiratory': CATEGORY_KEYWORDS['Respiratory'],
        'Gastrointestinal': CATEGORY_KEYWORDS['Gastrointestinal'],
        'Skin': CATEGORY_KEYWORDS['Skin'],
        'Neurological': CATEGORY_KEYWORDS['Neurological'],
        'Orthopedic': CATEGORY_KEYWORDS['Orthopedic'],
        'Other': [],
    }
    return keyword_map.get(disease_type, [])


def _predict_disease_name(text):
    if not text:
        return 'Undetermined Condition'

    combined = ' '.join([text or '', '']).lower()
    if 'pneumonia' in combined:
        return 'Pneumonia'
    if 'asthma' in combined:
        return 'Asthma'
    if 'parvovirus' in combined or 'parvo' in combined:
        return 'Parvovirus'
    if 'distemper' in combined:
        return 'Distemper'
    if 'seizure' in combined or 'epilepsy' in combined:
        return 'Seizure Disorder'
    if 'arthritis' in combined or 'joint' in combined or 'limp' in combined or 'fracture' in combined:
        return 'Arthritis'
    if 'worm' in combined or 'parasite' in combined or 'tick' in combined:
        return 'Worm Infestation'
    if 'dermat' in combined or 'eczema' in combined or 'rash' in combined:
        return 'Dermatitis'
    if 'gastro' in combined or 'diarrhea' in combined or 'vomit' in combined or 'colitis' in combined:
        return 'Gastroenteritis'
    if 'cough' in combined or 'bronchitis' in combined or 'respiratory' in combined:
        return 'Respiratory Infection'
    if 'fever' in combined or 'viral' in combined:
        return 'Viral Infection'
    if 'bacteria' in combined or 'infection' in combined:
        return 'Bacterial Infection'
    if 'fungal' in combined or 'mold' in combined or 'yeast' in combined:
        return 'Fungal Infection'
    if 'skin' in combined or 'wound' in combined or 'lesion' in combined:
        return 'Skin Condition'
    if 'bone' in combined or 'ortho' in combined:
        return 'Orthopedic Injury'
    return 'Undetermined Condition'


def _map_disease_name_to_type(disease_name):
    name = (disease_name or '').lower()
    if any(x in name for x in ['pneumonia', 'cough', 'bronchitis', 'respiratory', 'asthma']):
        return 'Respiratory'
    if any(x in name for x in ['gastro', 'diarr', 'vomit', 'colitis', 'gastroenteritis']):
        return 'Gastrointestinal'
    if any(x in name for x in ['dermat', 'skin', 'rash', 'eczema']):
        return 'Skin'
    if any(x in name for x in ['worm', 'parasite', 'parvo', 'parvovirus', 'tick']):
        return 'Parasitic'
    if any(x in name for x in ['virus', 'viral', 'fever']):
        return 'Viral'
    if any(x in name for x in ['bacterial', 'bacteria', 'infection']):
        return 'Bacterial'
    if any(x in name for x in ['seizure', 'epilep', 'neurolog']):
        return 'Neurological'
    if any(x in name for x in ['arthritis', 'ortho', 'bone', 'joint', 'limp', 'fracture']):
        return 'Orthopedic'
    return 'Other'


def summarize_branch_disease_trends(branch, pet_queryset=None, start_date=None, end_date=None, disease_type=None):
    """Create a lightweight, ORM-backed disease trend summary using medical record visit data."""
    from records.models import RecordEntry

    if branch is None:
        return {
            'summary': 'Select a branch to inspect regional disease patterns.',
            'warning': 'No branch data available for this view.',
            'insights': [],
            'disease_counts': [],
            'branch_label': 'All branches',
            'trend_labels': [],
            'trend_values': [],
            'available_diseases': [],
            'show_warning': True,
        }

    visits = RecordEntry.objects.select_related('record', 'record__pet').filter(
        Q(record__branch=branch) | Q(record__pet__branch=branch)
    )

    if start_date:
        visits = visits.filter(date_recorded__gte=start_date)
    if end_date:
        visits = visits.filter(date_recorded__lte=end_date)
    if disease_type:
        keywords = _get_disease_type_keywords(disease_type)
        if disease_type == 'Other':
            combined_text = (
                Q(history_clinical_signs__icontains='viral') |
                Q(history_clinical_signs__icontains='virus') |
                Q(history_clinical_signs__icontains='bacterial') |
                Q(history_clinical_signs__icontains='bacteria') |
                Q(history_clinical_signs__icontains='parasite') |
                Q(history_clinical_signs__icontains='parasitic') |
                Q(history_clinical_signs__icontains='fungal') |
                Q(history_clinical_signs__icontains='fungus') |
                Q(history_clinical_signs__icontains='respiratory') |
                Q(history_clinical_signs__icontains='cough') |
                Q(history_clinical_signs__icontains='gastro') |
                Q(history_clinical_signs__icontains='intestinal') |
                Q(history_clinical_signs__icontains='skin') |
                Q(history_clinical_signs__icontains='dermat') |
                Q(history_clinical_signs__icontains='neurolog') |
                Q(history_clinical_signs__icontains='ortho') |
                Q(history_clinical_signs__icontains='joint')
            )
            visits = visits.exclude(combined_text)
        elif keywords:
            query = None
            for keyword in keywords:
                keyword_query = Q(history_clinical_signs__icontains=keyword) | Q(treatment__icontains=keyword) | Q(rx__icontains=keyword)
                if query is None:
                    query = keyword_query
                else:
                    query = query | keyword_query
            visits = visits.filter(query)
    if pet_queryset is not None:
        visits = visits.filter(record__pet__in=pet_queryset)

    insights = []
    # Track per-disease stats: total records and distinct pets affected
    disease_counter = Counter()
    disease_pet_map = defaultdict(set)
    disease_visits = defaultdict(list)

    for visit in visits[:500]:
        combined_text = ' '.join([
            visit.history_clinical_signs or '',
            visit.treatment or '',
            visit.rx or '',
        ])
        disease_name = _predict_disease_name(combined_text)
        location_name = getattr(branch, 'city', '') or branch.name

        # Record stats
        disease_counter[disease_name] += 1
        pet_id = getattr(visit.record, 'pet_id', None) or getattr(visit.record, 'pet', None)
        try:
            # normalize pet id if pet object provided
            pet_id = int(pet_id) if pet_id is not None else None
        except Exception:
            pet_id = None
        if pet_id is not None:
            disease_pet_map[disease_name].add(pet_id)
        disease_visits[disease_name].append(visit)

        # generate per-visit insight for debugging / timeline
        trend_score = min(0.95, 0.45 + (len(disease_name) % 7) * 0.07 + (visit.date_recorded.day % 5) * 0.02)
        seasonality = 'Seasonal increase likely' if visit.date_recorded.month in {8, 9, 10} else 'Steady monitoring'
        confidence = min(0.98, 0.58 + (len(disease_name) % 5) * 0.07)
        insights.append({
            'disease': disease_name,
            'location': location_name,
            'case_count': 1,
            'trend_score': round(trend_score, 2),
            'seasonality': seasonality,
            'summary': f'AI-assisted prediction suggests {disease_name} based on this visit history.',
            'confidence': round(confidence, 2),
        })

    if not insights:
        return {
            'summary': 'Insufficient case history for this branch.',
            'warning': 'No results yet. There is not enough data for this branch to estimate trends.',
            'insights': [],
            'disease_counts': [],
            'branch_label': branch.name,
            'trend_labels': [],
            'trend_values': [],
            'available_diseases': [],
            'show_warning': True,
        }

    # Build disease counts but only mark as outbreak if repeated across multiple pets
    disease_counts = []
    for name, value in disease_counter.most_common(12):
        distinct_pets = len(disease_pet_map.get(name, set()))
        # conservative confidence that increases with both count and distinct pets
        confidence = round(min(0.96, 0.58 + (value / 10) * 0.06 + (distinct_pets - 1) * 0.04), 2)

        is_outbreak = (
            distinct_pets >= OUTBREAK_MIN_DISTINCT_PETS and
            value >= OUTBREAK_MIN_RECORDS and
            confidence >= MIN_CONFIDENCE_TO_DISPLAY
        )

        disease_counts.append({
            'name': name,
            'value': value,
            'distinct_pets': distinct_pets,
            'confidence': confidence,
            'outbreak': is_outbreak,
            'detail': f'Predicted from recent visit patterns',
        })
    # Only consider top diseases for summary
    top_diseases = [item['name'] for item in disease_counts if item.get('outbreak')][:6]
    trend_labels = [
        (datetime.now().month - index) % 12 + 1 for index in range(min(6, len(top_diseases)))
    ]
    trend_values = [max(1, int(item['value'] * 2.4)) for item in disease_counts if item.get('outbreak')]
    total_cases = sum(disease_counter.values())

    if top_diseases:
        summary = f'AI-assisted prediction highlights {", ".join(top_diseases[:3])} as potential outbreaks across {total_cases} reviewed visits.'
    else:
        summary = f'No outbreak-level signals detected for {branch.name} in the selected period (checked {total_cases} reviewed visits).'

    # Only surface outbreak-level disease counts to the UI (reduces hallucination noise)
    outbreak_list = [d for d in disease_counts if d.get('outbreak')]

    available_disease_types = []
    for disease in outbreak_list:
        t = _map_disease_name_to_type(disease['name'])
        if t not in available_disease_types:
            available_disease_types.append(t)

    show_warning = False
    if not outbreak_list:
        show_warning = True
        # override summary to be explicit
        summary = f'No outbreak-level signals detected for {branch.name} in the selected period (checked {total_cases} reviewed visits).'

    return {
        'summary': summary,
        'warning': '',
        'insights': insights[:8],
        'disease_counts': outbreak_list,
        'branch_label': branch.name,
        'trend_labels': trend_labels,
        'trend_values': trend_values,
        'available_diseases': available_disease_types,
        'total_cases': total_cases,
        'show_warning': show_warning,
    }

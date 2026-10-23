"""Bound model context without dropping source text or reference IDs."""
import json

MAX_MODEL_SOURCE_JSON = 9000
# Long-context API models (Gemini) can read a whole chapter or more per request.
LARGE_MODEL_SOURCE_JSON = 120_000
LOCATION_KEYS = {'type','page','slide','paragraph','table','row','cell','line','frame','heading',
                 'component_name','component_revision','character_start','unreadable_math',
                 'extraction_method','layout_unverified','location_unverified'}


def compact_sources(fragments):
    # Pixel observations and repeated OMML XML metadata stay in storage/review,
    # while the model receives the exact transcription and a short location.
    return [{**{k:v for k,v in f.items() if k!='locator'},
             **({'locator':{k:v[:200] if isinstance(v,str) else v for k,v in f['locator'].items()
                            if k in LOCATION_KEYS}} if 'locator' in f else {})} for f in fragments]


def source_json(fragments):
    return json.dumps(compact_sources(fragments), ensure_ascii=False)


def fits(fragments, budget=MAX_MODEL_SOURCE_JSON):
    return len(source_json(fragments)) <= budget

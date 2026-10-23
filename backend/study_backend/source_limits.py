"""Storage/extraction budgets are separate from a single model request."""
MAX_BYTES = 50 * 1024 * 1024
MAX_TEXT = 1_000_000
MAX_FRAGMENTS = 2000
MAX_COLLECTION_SOURCES = 20
MAX_AI_OUTLINE_FRAGMENTS = 16
MAX_UNIT_FRAGMENTS = 8
# An AI roadmap may make fuller lessons (Huy prefers fewer lessons that teach more);
# the per-request character budget still keeps each one small enough for a local model.
MAX_LESSON_FRAGMENTS = 16
MAX_UNITS = 400


def public_limits():
    return {
        'upload_bytes_per_file': MAX_BYTES,
        'extracted_characters_per_source': MAX_TEXT,
        'fragments_per_source': MAX_FRAGMENTS,
        'files_per_collection': MAX_COLLECTION_SOURCES,
        'native_pdf_pages': 1000,
        'native_pptx_slides': 1000,
        'ocr_pages_per_pass': 20,
        'native_ocr_continuation': True,
        'image_frames': 1000,
        'ocr_fragments_per_pass': 400,
        'ocr_characters_per_pass': 120_000,
        'office_image_occurrences_in_inventory': 200,
        'ai_outline_fragments_per_request': MAX_AI_OUTLINE_FRAGMENTS,
        'model_source_json_characters_per_request': 9000,
        'long_outline_strategy': 'source_sections_then_generate_each_unit',
        'unlimited_reading_or_generation': False,
    }

"""One bounded syntax normalization; no invented values or semantic/model retry."""
import hashlib
from pydantic import ValidationError


def without_trailing_commas(text):
    if len(text)>200_000:return text,0
    output=[];quoted=False;escaped=False;removed=0
    for index,char in enumerate(text):
        if quoted:
            output.append(char)
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True;output.append(char)
        elif char==',':
            following=index+1
            while following<len(text) and text[following] in ' \t\r\n':following+=1
            if following<len(text) and text[following] in ']}':
                removed+=1
                if removed>64:return text,0
            else:output.append(char)
        else:output.append(char)
    return ''.join(output),removed


def validated_json(schema,text,progress=None):
    try:return schema.model_validate_json(text)
    except ValidationError as original:
        if any(error['type']!='json_invalid' for error in original.errors(include_input=False)):raise
        normalized,count=without_trailing_commas(text)
        if not count:raise
        value=schema.model_validate_json(normalized)  # Same schema; malformed/invalid data still fails.
        if progress:
            progress.usage({'json_trailing_commas_removed':count,
                            'raw_json_sha256':hashlib.sha256(text.encode()).hexdigest(),
                            'normalized_json_sha256':hashlib.sha256(normalized.encode()).hexdigest()})
        return value

"""Short request-local citation labels, mapped exactly back to immutable IDs.

This is a transport codec, not reference repair: unknown labels and real IDs
outside the approved snapshot still fail. Source text and answers are untouched.
"""
import copy
import hashlib
import json
import re

from .models import SourceReferenceError, validate_refs
from .generation_contract import generation_schema, validated_generation
from .structured_output import validated_json


REFERENCE_CODEC_VERSION='scoped-reference-aliases-v1'


class ReferenceWire:
    def __init__(self,fragments):
        ids=[f['id'] for f in fragments]
        if len(set(ids))!=len(ids):raise ValueError('Phạm vi nguồn có ID trùng; chưa gọi AI.')
        self.originals=fragments
        self.encode={real:'R'+str(i+1) for i,real in enumerate(ids)}
        self.decode={alias:real for real,alias in self.encode.items()}
        self.fragments=[{**f,'id':self.encode[f['id']]} for f in fragments]

    def instruction(self,text):
        if self.encode:
            tokens='|'.join(re.escape(real) for real in sorted(self.encode,key=len,reverse=True))
            text=re.sub(r'(?<![A-Za-z0-9:_-])(?:'+tokens+r')(?![A-Za-z0-9:_-])',lambda m:self.encode[m[0]],text)
        return (text+'\nsource_refs chỉ nhận chính xác nhãn trong danh sách: '+json.dumps(list(self.decode))+'. '
                'Chép nhãn từ trường id của Nguồn, không tự đếm hoặc tạo nhãn mới. Không chèn nhãn kỹ thuật vào nội dung bài; chỉ dùng trong source_refs.')

    def schema(self,value):
        value=copy.deepcopy(value)
        def visit(node):
            if isinstance(node,dict):
                properties=node.get('properties',{})
                if 'source_refs' in properties and self.decode:
                    properties['source_refs']['items']={'type':'string','enum':list(self.decode)}
                for child in node.values():visit(child)
            elif isinstance(node,list):
                for child in node:visit(child)
        visit(value);return value

    def restore(self,value):
        if isinstance(value,list):return [self.restore(v) for v in value]
        if not isinstance(value,dict):return value
        result={}
        for key,item in value.items():
            if key=='source_refs':
                if not isinstance(item,list):raise SourceReferenceError(['invalid_ref_list'])
                invalid=[ref for ref in item if ref not in self.decode and ref not in self.encode]
                if invalid:raise SourceReferenceError(invalid)
                # Exact real IDs are accepted for backward-compatible adapters;
                # no ordinal/prefix/nearest-match inference is performed.
                result[key]=[self.decode.get(ref,ref) for ref in item]
            else:result[key]=self.restore(item)
        return result

    def validated(self,schema,text,progress=None):
        # First apply all wire shape/JSON checks, then decode references before
        # the existing source masks, ordering oracle and domain validators.
        candidate=validated_json(generation_schema(schema),text,progress).model_dump()
        restored=self.restore(candidate)
        value=validated_generation(schema,json.dumps(restored,ensure_ascii=False),progress,self.originals)
        validate_refs(value,set(self.encode))
        if progress:
            progress.usage({'reference_alias_count':len(self.encode),
                            'reference_alias_map_sha256':hashlib.sha256(json.dumps(self.encode,sort_keys=True).encode()).hexdigest()})
        return value

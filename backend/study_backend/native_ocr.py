"""Cancellable native processes for one OCR scope; never a model/provider call."""
import asyncio
import json
import math
from pathlib import Path
import tempfile

from .ocr import ROOT, binary
from .office_inputs import raster_asset


async def run_native(arguments, timeout_seconds=40):
    executable = await asyncio.to_thread(binary)
    process = await asyncio.create_subprocess_exec(str(executable), *map(str, arguments),
                                                  stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except (asyncio.CancelledError, TimeoutError):
        if process.returncode is None:
            try: process.terminate()
            except ProcessLookupError: pass
            try: await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                try: process.kill()
                except ProcessLookupError: pass
                await process.wait()
        raise
    if process.returncode:
        raise ValueError('Bộ OCR không đọc được phần đã chọn; nguồn gốc và kết quả trước vẫn được giữ.')
    if len(output) > 2_000_000:
        raise ValueError('Kết quả OCR quá lớn; chia phạm vi nhỏ hơn, chưa dùng phần này.')
    return output


async def count_frames(path):
    try:
        value = json.loads(await run_native(['image-info', path], 15))
        count = value['frames']
        if type(count) is not int or count < 1: raise ValueError('invalid frame count')
        return count
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ValueError('Chưa đọc được số khung ảnh; có thể mở bản gốc hoặc bổ sung bản chép tay.') from exc


def decode_scope(output, kind, index):
    """An empty detection is an observation, not proof that a page is blank."""
    try:
        packets = [json.loads(line) for line in output.splitlines()]
        field = 'page' if kind == 'page' else 'frame'
        matches = [packet for packet in packets if packet.get('kind') == field]
        if len(matches) != 1 or matches[0][field] != index: raise ValueError('scope mismatch')
        result = matches[0]
        observations = result['fragments']
        if not isinstance(observations,list) or len(observations)>2000: raise ValueError('observation limit')
        clean=[]
        for item in observations:
            locator=item['locator'];bounds=locator.get('bounds')
            if locator.get(field)!=index or not isinstance(item['text'],str) or not item['text'].strip():
                raise ValueError('invalid observation')
            if not isinstance(bounds,list) or len(bounds)!=4 or any(type(x) not in {int,float} or not math.isfinite(x) or not 0<=x<=1 for x in bounds):
                raise ValueError('invalid bounds')
            clean.append({'text':item['text'],'bounds':bounds,'recognizer_score':item.get('recognizer_score',0)})
        text='\n'.join(item['text'] for item in clean)
        if len(text)>120_000:raise ValueError('text limit')
        return {'text':text,'observations':clean,'engine':result['engine'],'revision':result['revision']}
    except (json.JSONDecodeError,KeyError,TypeError,ValueError) as exc:
        raise ValueError('OCR chưa trả bản đọc đúng phạm vi; không dùng kết quả này.') from exc


async def read_scope(path, kind, item, assets=None, timeout_seconds=40):
    if kind=='asset':
        image,_=await asyncio.to_thread(raster_asset,assets[item['key']])
        tmp=ROOT/'backend/runtime/ocr-tmp';tmp.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp) as folder:
            target=Path(folder)/'asset.png';target.write_bytes(image)
            output=await run_native(['image-frames',target,'1'],timeout_seconds)
        return decode_scope(output,'frame',1)
    field='page' if kind=='page' else 'frame'
    output=await run_native(['pdf-pages' if kind=='page' else 'image-frames',path,str(item['index'])],timeout_seconds)
    return decode_scope(output,field,item['index'])

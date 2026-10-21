"""Bounded UTF-8 framing shared by trusted configured inference transports."""
import codecs
import json


async def small_json(response):
    data = bytearray()
    async for chunk in response.aiter_bytes():
        data.extend(chunk)
        if len(data) > 8192: return {}
    try:
        value = json.loads(data)
        return value if isinstance(value, dict) else {}
    except ValueError: return {}


async def lines(response):
    decoder = codecs.getincrementaldecoder('utf-8')()
    pending = ''; total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > 2 * 1024 * 1024:
            raise ValueError('Luồng AI vượt giới hạn dữ liệu; chưa áp dụng đầu ra.')
        pending += decoder.decode(chunk)
        while '\n' in pending:
            line, pending = pending.split('\n', 1)
            if len(line) > 100_000: raise ValueError('Khung AI vượt giới hạn.')
            yield line.rstrip('\r')
        if len(pending) > 100_000: raise ValueError('Khung AI vượt giới hạn.')
    pending += decoder.decode(b'', final=True)
    if pending: yield pending.rstrip('\r')


async def ndjson(response):
    count = 0
    async for line in lines(response):
        if not line.strip(): continue
        count += 1
        if count > 8192: raise ValueError('Luồng AI có quá nhiều khung.')
        value = json.loads(line)
        if not isinstance(value, dict): raise ValueError('Khung AI không phải JSON object.')
        yield value


async def sse_json(response):
    data, count = [], 0
    async for line in lines(response):
        if line.startswith('data:'):
            data.append(line[5:].lstrip())
            if sum(map(len, data)) > 100_000: raise ValueError('Khung AI vượt giới hạn.')
        elif not line and data:
            count += 1
            if count > 8192: raise ValueError('Luồng AI có quá nhiều khung.')
            packet = '\n'.join(data); data = []
            if packet == '[DONE]': continue
            value = json.loads(packet)
            if not isinstance(value, dict): raise ValueError('Khung AI không phải JSON object.')
            yield value
    if data:
        value = json.loads('\n'.join(data))
        if not isinstance(value, dict): raise ValueError('Khung AI không phải JSON object.')
        yield value

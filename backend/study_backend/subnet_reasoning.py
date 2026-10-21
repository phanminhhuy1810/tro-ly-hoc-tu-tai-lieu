"""Computed IPv4 evidence and narrow claim guards; never repair an AI answer.

Only explicit single-CIDR claims are checked. This is not a semantic verifier
for arbitrary questions, multi-network designs, diagrams, or all math topics.
"""
import ipaddress
import json
import re
import unicodedata

IP = r'(?:\d{1,3}\.){3}\d{1,3}'
CIDR = re.compile(r'(?<![\d.])('+IP+r')\s*/\s*(\d{1,2})(?!\d)')
METHOD = 'python-ipaddress-ipv4-interface-v2'


def fold(text):
    text=unicodedata.normalize('NFKD', text.casefold()).replace('đ','d')
    return ''.join(c for c in text if not unicodedata.combining(c))


def calculations(text):
    values={}
    pairs=[(m[1],m[2]) for m in CIDR.finditer(text)]
    natural=re.compile(r'(?<![\d.])('+IP+r')\s*[,\(]?\s*(?:(?:voi|with|co|having)\s*)?(?:prefix|cidr|tien\s*to)\s*/?\s*(\d{1,2})(?!\d)')
    pairs.extend((m[1],m[2]) for m in natural.finditer(fold(text)))
    for address,prefix in pairs:
        try:
            given=ipaddress.IPv4Interface(address+'/'+prefix)
        except ValueError:
            continue
        network=given.network;size=network.num_addresses
        # ipaddress.hosts() treats /31 point-to-point and /32 host routes
        # differently; compute the same endpoints without enumerating a /0.
        first=int(network.network_address)+(1 if network.prefixlen<31 else 0)
        last=int(network.broadcast_address)-(1 if network.prefixlen<31 else 0)
        values[str(given)]={'given':str(given),'network':str(network.network_address),
            'broadcast':str(network.broadcast_address),'subnet_mask':str(network.netmask),
            'prefix':network.prefixlen,'host_bits':32-network.prefixlen,
            'network_full_octets':network.prefixlen//8,'network_remainder_bits':network.prefixlen%8,
            'boundary_octet':network.prefixlen//8+1 if network.prefixlen%8 else None,
            'total_addresses':size,'usable_hosts':max(1,size if network.prefixlen>=31 else size-2),
            'first_host':str(ipaddress.IPv4Address(first)),'last_host':str(ipaddress.IPv4Address(last))}
    return list(values.values())


def instruction(fragments):
    facts=[]
    for fragment in fragments:
        for value in calculations(fragment['text']):
            if any(f['given']==value['given'] for f in facts):continue
            facts.append({**value,'source_refs':[fragment['id']]})
    if not facts:return ''
    return ('\nPHÉP TÍNH TỪ DỮ KIỆN NGUỒN, DO BACKEND KIỂM TRA (không phải câu chép từ slide): '
            +json.dumps({'method':METHOD,'examples':facts[:8]},ensure_ascii=False)+
            '. Khi dùng đúng IP/prefix này, đáp án và lời giải phải khớp các phép tính trên. Một octet có8bit; '
            'prefix = 8*network_full_octets + network_remainder_bits, host_bits = 32-prefix. '
            'Nếu network_remainder_bits bằng0 thì ranh giới thẳng octet, không có octet chia dở. '
            'Nếu khác0 thì boundary_octet chứa đúng số bit network còn lại; không giữ nguyên cả octet đó rồi chỉ đổi octet cuối. '
            'Không dùng NetID sai để suy broadcast, dù một số kết quả khác đúng. Ví dụ mới phải tính lại theo đúng prefix. ')


class SubnetClaimError(ValueError):
    code='SUBNET_DERIVATION_MISMATCH'


NETWORK = r'(?:network(?:\s*(?:id|addr(?:ess)?))?|net\s*(?:id|addr(?:ess)?)|dia\s*chi\s*(?:network|mang))'
BROADCAST = r'(?:dia\s*chi\s*)?broadcast(?:\s*addr(?:ess)?)?'
MASK = r'(?:subnet\s*mask|mat\s*na\s*mang)'
BIT_LABELS = {
    'prefix': r'(?:net\s*id|network\s*id|phan\s*(?:mang|network)|so\s*bit\s*(?:mang|network))',
    'host_bits': r'(?:host\s*id|phan\s*host|so\s*bit\s*host)',
}
OCTET_DECOMPOSITION = re.compile(
    r'(?<!\d)(?P<total>\d{1,2})\s*bits?\s*(?:bao\s+phu|gom|chiem|covers?|comprises?|consists?\s+of)\s*'
    r'(?P<octets>\d)\s*(?:full\s+)?octets?\s*(?:dau|day\s*du)?\s*'
    r'(?:va|and|plus|\+)\s*(?P<bits>\d{1,2})\s*bits?\b')


def asserted(normal,start):
    # A quoted misconception/negation is not a positive numeric assertion.
    # Leave these cases to review instead of trying to interpret discourse.
    prefix=normal[max(0,start-60):start]
    return not re.search(r'\b(?:khong|not|nham|sai|wrong|incorrect|mistake)\b',prefix)


def check_bit_claims(normal,fact):
    for match in OCTET_DECOMPOSITION.finditer(normal):
        if asserted(normal,match.start()) and int(match['total'])!=8*int(match['octets'])+int(match['bits']):
            raise SubnetClaimError('Lời giải phân tích số bit thành octet không khớp: mỗi octet có8bit. Chưa dùng câu này; không tự sửa nội dung AI.')
    # Explicit counts belonging to another prefix in this text cannot be tied
    # to the stem's network. Arithmetic decomposition above is prefix-agnostic.
    prefixes={int(m[1]) for m in re.finditer(r'/\s*(\d{1,2})(?!\d)',normal)}
    if prefixes-set([fact['prefix']]):return
    for key,label in BIT_LABELS.items():
        patterns=[r'\b'+label+r'\s*(?:(?:co|la|is|has|=|:)\s*)?(\d{1,2})\s*bits?\b',
                  r'(?<!\d)(\d{1,2})\s*bits?\s*(?:(?:dau\s*(?:la\s*)?|thuoc|cho|of|trong|for|are|la)\s*)?'+label+r'\b']
        for pattern in patterns:
            for match in re.finditer(pattern,normal):
                if asserted(normal,match.start()) and int(match[1])!=fact[key]:
                    raise SubnetClaimError(f"Với {fact['given']}, {key} phải bằng{fact[key]}bit; AI ghi{match[1]}bit. Chưa dùng câu này.")


def check_question(question):
    """Reject proved conflicts in a stem/key/explanation; ignore distractors.

With several distinct CIDRs, a free-text address cannot safely be associated
with one network. Leave that case to ordinary source review instead of guessing.
"""
    # An exercise may deliberately quote an incorrect result and ask learners
    # to diagnose it. A numeric mismatch there is not proof that its key is
    # wrong; leave such semantic/error-analysis cases to source review.
    if re.search(r'\b(?:tinh\s+sai|sai\s+lam|nham\s+lan|khong\s+dung|khong\s+chinh\s+xac|incorrect|mistake|wrong|false)\b',fold(question['prompt'])):
        return
    facts=calculations(question['prompt'])
    if len(facts)!=1:return
    fact=facts[0]
    texts=[question['prompt'],question.get('explanation',''),*question.get('rubric',[])]
    if isinstance(question.get('answer'),str):texts.append(question['answer'])
    for text in texts:
        normal=fold(text)
        check_bit_claims(normal,fact)
        for label,key in ((NETWORK,'network'),(BROADCAST,'broadcast'),(MASK,'subnet_mask')):
            pattern=r'\b'+label+r'\s*(?:(?:la|is|=|:)\s*)?[\(\[]?\s*('+IP+r')(?!\d|\.\d)'
            for match in re.finditer(pattern,normal):
                if match[1]!=fact[key]:
                    raise SubnetClaimError(f"Câu có phép tính subnet sai: {fact['given']} cho {key} = {fact[key]}, nhưng AI ghi {match[1]}. Chưa dùng câu này; không tự sửa đáp án AI.")
    answer=question.get('answer')
    if not isinstance(answer,str):return
    key=answer.strip();stem=fold(question['prompt'])
    if re.fullmatch(r'\d+\s*(?:bits?)?',key,re.I):
        targets=[name for name,label in BIT_LABELS.items() if
                 re.search(label+r'\s*(?:(?:co|la|=|:)\s*)?_{3,}',stem) or
                 re.search(r'_{3,}\s*bits?\s*(?:(?:cho|thuoc|trong|of|for)\s*)?'+label,stem)]
        if len(targets)==1 and int(re.match(r'\d+',key)[0])!=fact[targets[0]]:
            raise SubnetClaimError(f"Đáp án số bit không khớp {fact['given']}: {targets[0]} = {fact[targets[0]]}. Chưa tự sửa đáp án AI.")
    if re.fullmatch(IP,key):
        asks_network=bool(re.search(NETWORK,stem));asks_broadcast='broadcast' in stem
        expected=fact['network'] if asks_network and not asks_broadcast else fact['broadcast'] if asks_broadcast and not asks_network else None
        if expected and key!=expected:
            raise SubnetClaimError(f"Đáp án subnet chưa đúng với {fact['given']}; chương trình tính {expected}, AI chọn {key}. Chưa dùng hoặc sửa tự động câu này.")
    host_count = re.search(r'hosts?\s*(?:hop\s*le|dung\s*duoc|kha\s*dung)|(?:usable|valid)\s*hosts?',stem)
    if re.fullmatch(r'\d+\s*(?:hosts?)?',key,re.I) and host_count and re.search(r'bao nhieu|how many|____',stem):
        given=int(re.match(r'\d+',key)[0])
        if given!=fact['usable_hosts']:
            raise SubnetClaimError(f"Số host dùng được của {fact['given']} là {fact['usable_hosts']}, AI ghi {given}. Chưa dùng câu này.")

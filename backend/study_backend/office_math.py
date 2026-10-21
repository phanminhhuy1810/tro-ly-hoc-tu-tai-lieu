"""Conservative OMML to LaTeX transcription, without evaluating mathematics."""
import hashlib
from lxml import etree

M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
UNREADABLE = '[Công thức Office Math chưa đọc được — cần sửa tay hoặc bỏ khỏi phạm vi]'


class UnsupportedMath(ValueError):
    pass


def name(node):
    return etree.QName(node).localname


def child(node, local):
    return None if node is None else node.find('{'+M+'}'+local)


def attribute(node, key, default=''):
    return default if node is None else node.get('{'+M+'}'+key, default)


def transcribe(node, index):
    info={'index':index, 'xml_sha256':hashlib.sha256(etree.tostring(node)).hexdigest(),
          'reader':'omml-common-v1', 'accuracy_verified':False}
    try:
        if sum(1 for _ in node.iter()) > 500: raise UnsupportedMath('node_limit')
        value=render(node)
        if not value.strip(): raise UnsupportedMath('empty_expression')
        info.update(supported=True, latex=value)
        return r'\('+value+r'\)', info
    except UnsupportedMath as exc:
        info.update(supported=False, reason=str(exc))
        return UNREADABLE, info


def render(node, depth=0):
    if node is None: raise UnsupportedMath('missing_component')
    if depth>20: raise UnsupportedMath('depth_limit')
    tag=name(node)
    def sub(local): return render(child(node,local),depth+1)
    def contents(): return ''.join(render(x,depth+1) for x in node)
    if tag.endswith('Pr') or tag in {'ctrlPr','rPr'}: return ''
    if tag=='t':
        text=node.text or ''
        escaped={'\\':r'\backslash ', '{':r'\{', '}':r'\}', '%':r'\%', '#':r'\#', '&':r'\&', '$':r'\$', '_':r'\_', '^':r'\hat{}'}
        return ''.join(escaped.get(c,{'−':'-','×':r'\times ','÷':r'\div ','∞':r'\infty '}.get(c,c)) for c in text)
    if tag in {'oMath','oMathPara','r','e','num','den','sup','sub','deg','fName','lim','mr'}: return contents()
    if tag=='f':
        kind=attribute(child(child(node,'fPr'),'type'),'val','bar')
        if kind not in {'bar','lin'}: raise UnsupportedMath('fraction_layout_'+kind)
        return r'\frac{'+sub('num')+'}{'+sub('den')+'}'
    if tag=='sSup': return '{'+sub('e')+'}^{'+sub('sup')+'}'
    if tag=='sSub': return '{'+sub('e')+'}_{'+sub('sub')+'}'
    if tag=='sSubSup': return '{'+sub('e')+'}_{'+sub('sub')+'}^{'+sub('sup')+'}'
    if tag=='rad':
        hidden=attribute(child(child(node,'radPr'),'degHide'),'val','0') in {'1','true','on'}
        degree='' if hidden or child(node,'deg') is None else sub('deg')
        return r'\sqrt'+('['+degree+']' if degree else '')+'{'+sub('e')+'}'
    if tag=='nary':
        props=child(node,'naryPr');symbol=attribute(child(props,'chr'),'val','∫')
        operator={'∫':r'\int','∑':r'\sum','∏':r'\prod','⋂':r'\bigcap','⋃':r'\bigcup'}.get(symbol)
        if not operator: raise UnsupportedMath('nary_operator')
        lower='' if child(node,'sub') is None or attribute(child(props,'subHide'),'val') in {'1','true','on'} else sub('sub')
        upper='' if child(node,'sup') is None or attribute(child(props,'supHide'),'val') in {'1','true','on'} else sub('sup')
        return operator+('_{'+lower+'}' if lower else '')+('^{'+upper+'}' if upper else '')+' '+sub('e')
    if tag=='d':
        props=child(node,'dPr');opening=attribute(child(props,'begChr'),'val','(');closing=attribute(child(props,'endChr'),'val',')');separator=attribute(child(props,'sepChr'),'val','|')
        delimiters={'(': '(',')':')','[':'[',']':']','{':r'\{','}':r'\}','|':'|','':'.'}
        if opening not in delimiters or closing not in delimiters or separator not in {'|',',',';'}: raise UnsupportedMath('delimiter')
        items=[render(x,depth+1) for x in node if name(x)=='e']
        if not items: raise UnsupportedMath('missing_delimited_expression')
        return r'\left'+delimiters[opening]+separator.join(items)+r'\right'+delimiters[closing]
    if tag=='func': return r'\operatorname{'+sub('fName')+'}'+sub('e')
    if tag=='m':
        rows=[]
        for row in node:
            if name(row)=='mr': rows.append(' & '.join(render(x,depth+1) for x in row if name(x)=='e'))
        if not rows: raise UnsupportedMath('empty_matrix')
        return r'\begin{matrix}'+r' \\ '.join(rows)+r'\end{matrix}'
    if tag=='bar':
        position=attribute(child(child(node,'barPr'),'pos'),'val','top')
        if position not in {'top','bot'}: raise UnsupportedMath('bar_position')
        return (r'\overline{' if position=='top' else r'\underline{')+sub('e')+'}'
    if tag=='acc':
        symbol=attribute(child(child(node,'accPr'),'chr'),'val','̂')
        command={'̂':r'\hat','^':r'\hat','⃗':r'\vec','̄':r'\bar','̇':r'\dot','̈':r'\ddot'}.get(symbol)
        if not command: raise UnsupportedMath('accent')
        return command+'{'+sub('e')+'}'
    raise UnsupportedMath('element_'+tag)

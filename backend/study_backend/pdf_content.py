"""Bounded visual-content signals, not a PDF layout or formula recognizer."""
import math
from pypdf.generic import ContentStream
from pypdf.errors import PdfReadError

MAX_PDF_PAGES = 1000
MAX_OCR_PAGES = 20
MAX_IMAGE_FRAMES = 1000


def multiply(a, b):
    return [a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3],
            a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3],
            a[4]*b[0]+a[5]*b[2]+b[4], a[4]*b[1]+a[5]*b[3]+b[5]]


def visual_signals(page):
    box = page.cropbox
    left, bottom, width, height = map(float, (box.left, box.bottom, box.width, box.height))
    if not all(math.isfinite(x) for x in (left,bottom,width,height)) or min(width, height) <= 0:
        return {'analysis_incomplete': True}
    regions, lines, operations, incomplete = [], 0, 0, False

    def walk(stream, resources, matrix, active=()):
        nonlocal lines, operations, incomplete
        if len(active) >= 8: incomplete = True; return
        if hasattr(resources, 'get_object'): resources = resources.get_object()
        stack = []
        content = stream if isinstance(stream, ContentStream) else ContentStream(stream, page.pdf)
        for args, op in content.operations:
            operations += 1
            if operations > 50_000: incomplete = True; return
            if op == b'q': stack.append(matrix[:])
            elif op == b'Q':
                if stack: matrix = stack.pop()
                else: incomplete = True
            elif op == b'cm':
                if len(args) != 6: incomplete = True; continue
                matrix = multiply([float(x) for x in args], matrix)
                if not all(math.isfinite(x) for x in matrix): incomplete = True; return
            elif op in {b'l', b'c', b'v', b'y'}: lines += 1
            elif op in {b'Do', b'INLINE IMAGE'}:
                obj = None
                if op == b'Do':
                    objects = resources.get('/XObject', {})
                    if hasattr(objects, 'get_object'): objects = objects.get_object()
                    obj = objects.get(args[0])
                    if obj is None: incomplete = True; continue
                    obj = obj.get_object()
                if obj is not None and obj.get('/Subtype') == '/Form':
                    identity = id(obj)
                    if identity in active: incomplete = True; continue
                    walk(obj, obj.get('/Resources', resources),
                         multiply([float(x) for x in obj.get('/Matrix', [1,0,0,1,0,0])], matrix), active + (identity,))
                elif obj is None or obj.get('/Subtype') == '/Image':
                    points = [(x*matrix[0]+y*matrix[2]+matrix[4], x*matrix[1]+y*matrix[3]+matrix[5]) for x,y in [(0,0),(0,1),(1,0),(1,1)]]
                    x1, y1 = max(left, min(x for x,y in points)), max(bottom, min(y for x,y in points))
                    x2, y2 = min(left+width, max(x for x,y in points)), min(bottom+height, max(y for x,y in points))
                    if (x2-x1)*(y2-y1)/(width*height) >= .06 and x2 > x1 and y2 > y1:
                        if len(regions) < 32: regions.append([round((x1-left)/width, 5), round((y1-bottom)/height, 5), round((x2-x1)/width, 5), round((y2-y1)/height, 5)])
                        else: incomplete = True
    try:
        content = page.get_contents()
        if content is not None: walk(content, page.get('/Resources', {}), [1,0,0,1,0,0])
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError, PdfReadError):
        incomplete = True
    value = {}
    if regions: value['raster_regions'] = regions; value['bounds_coordinate_system'] = 'normalized_bottom_left'
    if lines >= 30: value['vector_paths'] = lines
    if incomplete: value['analysis_incomplete'] = True
    return value

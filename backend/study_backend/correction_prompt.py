"""Question repair inputs are facts to reconsider, not a previous answer key.

The complete old answer remains in proposal/version storage. Omitting it from
one model request is not source repair, an answer validator, or a quality proof.
"""
import json

from .generation_contract import question_fields
from .language import language_instruction
from .question_generation import RULES, content_preferences

INPUT_STRATEGY = 'question-inputs-without-old-solution-v1'
FULL_CONTENT_STRATEGY = 'full-selected-content-v1'
LEGACY_STRATEGY = 'legacy-full-selected-content'


def question_prompt(prefs, unit, before, request, chapter_instruction):
    kind = before['kind']
    inputs = {k: before[k] for k in ('kind', 'prompt', 'options', 'left')}
    task = {'request': request, 'question_inputs': inputs,
            'preferences': content_preferences(prefs),
            'unit': {k: unit[k] for k in ('title', 'objective')}}
    return ('SỬA MỘT CÂU ĐANG CÓ, CHƯA ÁP DỤNG. Tự suy lại từ dữ kiện của đề và nguyên lý trong nguồn; '
            'không suy rằng kết luận cũ đúng. Key/lời giải/rubric cũ được giữ ở hệ thống để so sánh, không gửi làm căn cứ cho lượt này. '
            'Yêu cầu sửa hiện tại xác định phần cần sửa. Nếu chỉ sửa lời giải/đáp án, giữ nguyên đề, các lựa chọn và đối tượng đang xét. '
            'Không thêm một hành động, điều kiện hay dữ kiện vào lời giải mà đề không nêu. '
            + json.dumps(task, ensure_ascii=False) + language_instruction(prefs) + chapter_instruction
            + '\nTrước khi kết luận, kiểm tra: dữ kiện nào thực sự có trong đề; nguyên lý nào trong nguồn cho phép kết luận; còn thiếu điều kiện nào. '
            'Nếu thiếu dữ kiện để kết luận duy nhất, không lấp chỗ thiếu bằng suy đoán. Với short_answer, đáp án tham khảo có thể nêu chưa đủ dữ kiện, '
            'giải thích điều kiện nào thiếu và rubric cho việc nhận ra giới hạn đó. Với dạng có đáp án cố định, trả question=null và reason khi không có đáp án duy nhất có căn cứ. '
            'Bản tổng hợp chương định hướng, source_refs phải dẫn đúng nguyên văn trong danh sách Nguồn của request, không suy nhãn nguồn từ bản tóm tắt. '
            'Không đưa nhãn trích dẫn kỹ thuật vào prompt/answer/explanation. Công thức dùng văn bản x^2, sqrt(x), không dùng lệnh LaTeX/backslash. '
            '\nTrả một object question/reason, chỉ một câu cùng dạng ' + kind + '. ' + RULES[kind]
            + ' question chỉ có các trường: ' + ', '.join(question_fields(kind))
            + '. Không thêm id/type/difficulty hoặc trường của dạng khác. Explanation tối đa70từ. Không viết nhận định cũ thành dữ kiện mới.')


def with_creator_metadata(candidate, before):
    return {**candidate, **{key: before.get(key) for key in ('difficulty', 'difficulty_basis')}}

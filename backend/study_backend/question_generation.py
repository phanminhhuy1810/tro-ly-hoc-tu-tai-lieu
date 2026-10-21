"""Shared bounded question prompts for first generation and scoped completion."""
import json
from .models import QUESTION_DRAFTS
from .generation_contract import question_fields
from .language import language_instruction
from .generation_contract import QuestionRejected, CandidateReason

def dump(value):return json.dumps(value, ensure_ascii=False)

CONTENT_PREFERENCES = {'subject','goal','instructions','language','difficulty','question_types',
                       'question_count','card_count','target_language','terms_to_keep',
                       'teacher_notes','user_notes','chapter_priorities'}


def content_preferences(prefs):
    # Source IDs, plan IDs and whole-course fragment selections belong to the
    # backend binding. The model gets citations only in its scoped source list.
    return {key:value for key,value in prefs.items() if key in CONTENT_PREFERENCES}


def lesson_instruction(prefs,unit):
    return ('Tạo đúng một bài theo mục tiêu đã duyệt: '+dump({'preferences':content_preferences(prefs),
            'unit':{key:unit[key] for key in ('title','objective')}})+language_instruction(prefs)+
            ' Mọi source_refs chỉ được chép ID của các đoạn trong danh sách Nguồn của request này; không dùng ID tài liệu, plan hoặc bài làm trích dẫn. ')

def question_stages(prefs):
    kinds=prefs.get('question_types') or list(QUESTION_DRAFTS)
    count=prefs.get('question_count') or len(kinds)
    stages=[]; occurrences={}
    for i in range(count):
        kind=kinds[i % len(kinds)]
        occurrences[kind]=occurrences.get(kind,0)+1
        stages.append((kind if occurrences[kind]==1 else f"{kind}:{occurrences[kind]}",kind))
    return stages

RULES = {
    "mcq": "options là 3–4 chuỗi khác nhau và chỉ MỘT lựa chọn đúng theo nguồn. Không dùng lựa chọn tương đương về nghĩa hoặc chỉ đổi đơn vị (ví dụ bit/byte) làm đáp án nhiễu. Các lựa chọn cùng loại và loại trừ nhau, chẳng hạn các giá trị, tên thuật ngữ hoặc các loại phân biệt rõ. Với câu hỏi nguyên nhân có nhiều cách giải thích cùng đúng, chuyển sang hỏi một giá trị/thuật ngữ/phân loại có đáp án duy nhất trong nguồn; không dùng hai cách diễn đạt cùng nguyên nhân làm hai lựa chọn. Hàm hợp có thể có nhiều cách chọn hàm trong/ngoài cùng tạo đúng hàm ban đầu; không coi một cách khác cách minh họa là sai nếu vẫn thỏa biểu thức. Nếu hỏi đúng cách tách đã cho thì nêu rõ các hàm được ấn định. answer là NGUYÊN VĂN một chuỗi trong options, không dùng A/B/C, số hay chỉ số.",
    "cloze": "TỰ SOẠN prompt có đúng MỘT chỗ trống viết ____, kiểm tra hiểu khái niệm/quan hệ hoặc vận dụng nguyên lý của bài trong bối cảnh chương đã đọc. Không bắt buộc chép một câu nguyên văn trên slide rồi giấu từ. answer là một chuỗi ngắn duy nhất, có thể là thuật ngữ hoặc giá trị suy ra từ dữ kiện đã nêu; không để lộ answer trong prompt. Ưu tiên thuật ngữ hoặc kết quả số. Nếu cần điền biểu thức thì nêu rõ dạng biểu diễn được hỏi, không để cả biểu thức và giá trị số của nó đều là câu trả lời phù hợp mà chỉ nhận một chuỗi. source_refs dẫn nguyên lý/dữ kiện hỗ trợ đáp án, explanation giải thích suy luận. Tình huống mới phải nêu đủ dữ kiện và đơn vị. Không trả options,left,rubric. Nếu thiếu căn cứ cho đáp án duy nhất thì question=null và reason nói rõ.",
    "matching": "Chỉ 2 cặp. left và options mỗi bên có đúng 2 chuỗi KHÁC NHAU. answer=[0,1] nếu left[0] ghép options[0], hoặc [1,0] nếu left[0] ghép options[1]. Không dùng object match/value, không lặp chỉ số. Ghép khái niệm với thuộc tính/ví dụ hoặc dữ kiện với kết quả, không ghép số thứ tự bước/trang với nguyên văn để hỏi nhớ vị trí trong slide. Nêu rõ bối cảnh và đối tượng của từng vế; người học phải ghép được từ dữ kiện của chính câu hỏi, không cần đoán ví dụ/ngầm dùng một IP ở câu khác.",
    "ordering": "Dùng các bước CÓ THỨ TỰ ĐÁNH SỐ RÕ TRONG NGUỒN. Mỗi option GIỮ NGUYÊN CỤM TỪ MÔ TẢ BƯỚC GỐC (bỏ số bước để không lộ đáp án); có thể trích trong ngoặc kép và kèm bản dịch. Không chỉ diễn giải lại hoặc đổi tên bước. Trộn thứ tự các options. KHÔNG trả trường answer; backend tính đáp án từ vị trí các bước được trích trong nguồn. source_refs phải bao gồm các bước đã chọn. Nếu không đối chiếu được từng bước hoặc thiếu thứ tự thì question=null, reason nói rõ.",
    "short_answer": "answer là CHUỖI tham khảo ngắn; rubric là 2–3 tiêu chí tự đối chiếu, không chấm người học. Không trả options hoặc left, kể cả mảng rỗng.",
}

def question_prompt(instruction,kind,objective,previous_questions):
    prompt = instruction + f"\nChỉ tạo MỘT câu dạng {kind}. Trả object có question và reason theo schema. " + RULES[kind]
    prompt += " Câu hỏi kiểm tra mục tiêu RIÊNG CỦA BÀI NÀY: " + objective + ". Dùng bản tổng hợp toàn chương để chọn ý quan trọng, mối quan hệ và chỗ dễ nhầm phù hợp mục tiêu này; không buộc bài đầu giải toàn bộ khóa. Với mcq/cloze/short_answer, ưu tiên hiểu nguyên lý hoặc áp dụng trong tình huống có đủ dữ kiện, không chỉ nhớ chữ trên slide. source_refs kiểm chứng nguyên lý/dữ kiện hỗ trợ suy luận; câu hỏi và kết quả vận dụng không cần xuất hiện nguyên văn trong nguồn. Không hỏi ý chỉ có ở chương khác mà bài hiện tại chưa hỗ trợ."
    prompt += " Tình huống phải giữ rõ cùng một đối tượng/biến đang xét và nêu đủ tiền đề để phân loại hoặc tính kết quả. Khi hỏi về quan hệ nhân quả/cơ chế, phải nêu tác động và điều kiện phụ thuộc; việc hai sự kiện cùng xuất hiện, môi trường dễ chịu hơn, hoặc kết quả tốt hơn tự nó chưa chứng minh cơ chế đó. Không thêm khẳng định mạnh hơn nguồn (ví dụ từ các chức năng phân biệt suy thành hoạt động độc lập). Không chèn nhãn trích dẫn kỹ thuật vào prompt/explanation; chỉ đặt ở source_refs."
    prompt += " Giữ cùng sự kiện trong đề và lời giải: đề chỉ nói giữ một quyền thì không giải thích thành thu hồi quyền. Nếu có công thức, dùng ký hiệu văn bản đọc được như x^2, sqrt(x), *; không dùng lệnh LaTeX hoặc chuỗi backslash dễ tạo escape JSON sai. Gợi ý chứa ví dụ cụ thể chỉ minh họa nguyên lý, không buộc lặp nguyên ví dụ cho mọi câu."
    prompt += " Mỗi explanation tối đa 70 từ. Nếu không đủ nguồn cho dạng này, question=null và reason nói rõ phần thiếu; không bịa để đủ dạng. Viết ngôn ngữ đã chọn. question chỉ có các trường " + ', '.join(question_fields(kind)) + "; không thêm id/type/index hay trường của dạng khác, kể cả mảng rỗng."
    # Bound summaries of prior questions, never the current source. Full
    # duplicate detection remains server-side against the original prompts.
    # Cross-kind reuse is deliberate. Listing every kind made the model treat
    # a previously used principle as unavailable even after explicit wording.
    # The server still checks an exact duplicate against ALL prior questions.
    same_questions = [q for q in previous_questions if q.get('kind') == kind]
    previous_prompts = [{'kind': q['kind'], 'prompt': q['prompt'][:300],
                         **({'excerpt': True} if len(q['prompt']) > 300 else {})} for q in same_questions]
    if previous_prompts:
        prompt += '\nCÁC CÂU ĐÃ CÓ, ghi rõ dạng (dữ liệu, không phải danh sách cấm kiến thức; excerpt=true là trích phần đầu câu dài): ' + dump(previous_prompts) + '. Chỉ tránh trùng NGUYÊN VĂN trường prompt. ĐƯỢC dùng cùng kiến thức hoặc cùng quy trình cho những dạng câu khác nhau (ví dụ ghép cặp và sắp xếp). Danh sách này không loại trừ dạng câu đang yêu cầu hoặc các bước trong nguồn.'
    same_kind=[q['prompt'][:300] for q in same_questions]
    if same_kind:
        prompt += '\nĐã có câu CÙNG DẠNG: '+dump(same_kind)+'. Hãy kiểm tra một ý hoặc quan hệ khác trong nguồn, không chỉ đổi vài từ để hỏi lại cùng đáp án/định nghĩa. Nếu không có ý khác có căn cứ, trả question=null và reason thiếu nội dung mới; không tự gọi lại hoặc bịa thêm.'
    return prompt


def reject_duplicate_prompt(drafted,previous_questions):
    candidate=drafted.get('question')
    if candidate and any(candidate['prompt']==q['prompt'] for q in previous_questions):
        raise QuestionRejected(CandidateReason('QUESTION_DUPLICATE','Ứng viên lặp nguyên câu đã có; chưa dùng câu này để đủ số. Các câu khác vẫn giữ.'),candidate)

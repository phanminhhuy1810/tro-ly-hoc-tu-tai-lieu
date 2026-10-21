"""Freeze original evaluation notes before any output is generated.

These are agent-authored teaching notes and new worked examples, not copied
book text or independent instructor labels. Public sources verify general facts;
math/IP oracles are separate from the generation prompt and server answer key.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RFC = 'https://www.rfc-editor.org/rfc/'
OS = 'https://openstax.org/books/'
TYPES = ['mcq', 'cloze', 'matching', 'ordering', 'short_answer']


def case(id, split, subject, title, goal, text, facts, references, ordering=True, terms=None):
    return dict(id=id, split=split, subject=subject, title=title, goal=goal, text=text,
                expected_facts=facts, references=references,
                expected_source_ordering=ordering, question_types=TYPES,
                question_count=8, card_count=2, language='vi', difficulty='applied',
                terms_to_keep=terms or [],
                source_kind='original_agent_authored_evaluation_notes_not_book_excerpt',
                label_status='computational_or_source_crosschecked_agent_labels_need_independent_review')


CASES = [
case('net-dev-prefix', 'dev', 'Mạng máy tính', 'IPv4 và subnet /25',
     'Phân biệt prefix, số địa chỉ, network, broadcast và host dùng được trong ví dụ /25.',
'''IPv4 dài 32 bit. Với prefix /25, phần mạng có 25 bit và phần host có 7 bit. Một subnet /25 có 128 địa chỉ; trong subnet thông thường này có 126 địa chỉ host dùng được khi bỏ hai biên.
Ví dụ 10.12.7.201/25: network là 10.12.7.128, broadcast là 10.12.7.255. Dải host dùng được là 10.12.7.129 đến 10.12.7.254. Subnet mask là 255.255.255.128.
Quy trình tìm hai biên từ một IPv4/prefix:
1. Đọc prefix để xác định số bit host.
2. Tính kích thước khối địa chỉ từ số bit host.
3. Tìm khối chứa địa chỉ đã cho.
4. Lấy đầu khối làm network và cuối khối làm broadcast.
5. Bỏ hai biên để lấy dải host dùng được.''',
     {'oracle': 'ipv4', 'input': '10.12.7.201/25'},
     [RFC+'rfc4632.html#section-3.1']),
case('calc-dev-ftc', 'dev', 'Vi tích phân', 'Tích phân xác định và hai cận',
     'Dùng nguyên hàm và hai cận để tính tích phân; phân biệt giá trị tại cận với hiệu hai giá trị.',
'''Nếu f liên tục trên [a,b] và F là một nguyên hàm của f thì tích phân từ a đến b của f(x) dx bằng F(b)-F(a). Không lấy F(a)-F(b).
Với f(x)=x^2, chọn F(x)=x^3/3. Trên [0,2], F(2)=8/3 và F(0)=0, nên tích phân bằng 8/3. Đổi cận từ 2 về 0 cho kết quả -8/3. Với g(x)=2x+1 trên [0,1], nguyên hàm G(x)=x^2+x và tích phân bằng 2.
Quy trình tính tích phân xác định bằng nguyên hàm:
1. Tìm một nguyên hàm của hàm dưới dấu tích phân.
2. Tính giá trị nguyên hàm tại cận trên.
3. Tính giá trị nguyên hàm tại cận dưới.
4. Lấy giá trị tại cận trên trừ giá trị tại cận dưới.''',
     {'oracle': 'polynomial_integral', 'coefficients': [0,0,1], 'bounds': [0,2], 'result': '8/3', 'reversed': '-8/3', 'second_coefficients': [1,2], 'second_bounds': [0,1], 'second_result': '2'},
     [OS+'calculus-volume-1/pages/5-3-the-fundamental-theorem-of-calculus']),
case('psy-dev-operant', 'dev', 'Tâm lý đại cương', 'Củng cố và trừng phạt',
     'Phân biệt thêm/bớt kích thích với tăng/giảm hành vi, đặc biệt negative reinforcement không phải punishment.',
'''Trong operant conditioning, reinforcement chỉ hậu quả làm tăng khả năng hành vi được lặp lại; punishment chỉ hậu quả làm giảm khả năng đó. Positive nghĩa là thêm một kích thích, negative nghĩa là loại bỏ một kích thích; chúng không có nghĩa là tốt và xấu.
Positive reinforcement là thêm kích thích để tăng hành vi. Negative reinforcement là loại bỏ kích thích để tăng hành vi. Positive punishment là thêm kích thích để giảm hành vi. Negative punishment là loại bỏ kích thích để giảm hành vi.
Trong ví dụ giả định, tiếng còi khó chịu ngừng khi người lái cài dây an toàn và việc cài dây trở nên thường xuyên hơn: đó là negative reinforcement. Tặng điểm sau khi học khiến việc học tăng lên là positive reinforcement. Thu hồi quyền chơi sau vi phạm khiến vi phạm giảm là negative punishment.
Quy trình phân loại một ví dụ đã có dữ kiện:
1. Xác định hành vi mục tiêu cần xét.
2. Xác định dữ kiện nói hành vi tăng hay giảm.
3. Xác định hậu quả thêm hay loại bỏ kích thích.
4. Kết hợp hai chiều để gọi tên loại hậu quả.''',
     {'oracle': 'concept_table', 'relations': {'positive reinforcement': ['add','increase'], 'negative reinforcement': ['remove','increase'], 'positive punishment': ['add','decrease'], 'negative punishment': ['remove','decrease']}, 'seatbelt': 'negative reinforcement', 'loss_of_play': 'negative punishment'},
     [OS+'psychology-2e/pages/6-3-operant-conditioning'], terms=['reinforcement','punishment','positive','negative']),
case('net-dev-ipv6', 'dev', 'Mạng máy tính', 'Biểu diễn địa chỉ IPv6',
     'Đọc độ dài, các nhóm hextet, địa chỉ loopback/unspecified và cách rút gọn một địa chỉ IPv6.',
'''IPv6 dùng địa chỉ 128 bit. Cách viết đầy đủ có tám nhóm hexadecimal 16 bit, mỗi nhóm thường gọi là hextet. Có thể bỏ các số 0 ở đầu một nhóm. Ký hiệu :: thay cho một dãy nhóm 0 và chỉ xuất hiện nhiều nhất một lần trong một địa chỉ để tránh mơ hồ.
Địa chỉ ::1 là loopback. Địa chỉ :: là unspecified. IPv6 không có broadcast; multicast phục vụ các nhóm thiết bị. Với ví dụ 2001:db8:0000:0000:0000:0000:0000:0001, dạng rút gọn là 2001:db8::1.
Quy trình rút gọn ví dụ trên:
1. Chia địa chỉ đầy đủ thành tám nhóm hexadecimal.
2. Bỏ các số 0 ở đầu mỗi nhóm nhưng giữ nhóm 0 là 0.
3. Thay dãy nhóm 0 liên tiếp dài nhất bằng một dấu ::.
4. Kiểm tra dạng rút gọn vẫn biểu diễn đúng 128 bit ban đầu.''',
     {'oracle': 'ipv6', 'input': '2001:db8:0000:0000:0000:0000:0000:0001', 'loopback': '::1', 'unspecified': '::', 'bits':128, 'groups':8},
     [RFC+'rfc4291.html#section-2.2', RFC+'rfc4291.html#section-2.5'], terms=['IPv6','hextet','loopback','unspecified','multicast']),
case('calc-dev-chain', 'dev', 'Vi tích phân', 'Đạo hàm hàm hợp',
     'Áp dụng chain rule, giữ nhân đạo hàm hàm trong; tính đạo hàm và giá trị tại điểm trong ví dụ.',
'''Nếu h(x)=f(g(x)) và các hàm khả vi tại những điểm cần xét, chain rule cho h'(x)=f'(g(x))*g'(x). Đạo hàm hàm ngoài phải được tính tại g(x), không phải tại g'(x).
Ví dụ h(x)=(3x+1)^4: hàm trong g(x)=3x+1 có g'(x)=3; hàm ngoài f(u)=u^4 có f'(u)=4u^3. Do đó h'(x)=12(3x+1)^3 và h'(0)=12. Biểu thức 4(3x+1)^3 bỏ mất hệ số 3 nên sai.
Quy trình dùng chain rule:
1. Xác định hàm trong và hàm ngoài.
2. Lấy đạo hàm hàm ngoài rồi thế hàm trong vào.
3. Tính đạo hàm hàm trong.
4. Nhân hai kết quả để được đạo hàm hàm hợp.''',
     {'oracle': 'chain_power', 'inner_slope':3, 'inner_intercept':1, 'power':4, 'at':0, 'coefficient':12, 'value_at':12, 'expression':"12*(3*x+1)^3"},
     [OS+'calculus-volume-1/pages/3-6-the-chain-rule'], terms=['chain rule']),
case('psy-dev-memory', 'dev', 'Tâm lý đại cương', 'Ba chức năng của trí nhớ',
     'Phân biệt encoding, storage, retrieval và các kiểu mã hóa; không coi ví dụ nhớ lại là mã hóa.',
'''Encoding là quá trình đưa thông tin vào hệ thống trí nhớ. Storage là lưu giữ thông tin đã được mã hóa. Retrieval là đưa thông tin đã lưu trở lại nhận thức. Ba thuật ngữ mô tả các chức năng khác nhau; đây không phải bản hướng dẫn thao tác từng bước.
Semantic encoding xử lý ý nghĩa; visual encoding xử lý hình ảnh; acoustic encoding xử lý âm thanh. Nhận ra ý nghĩa của một từ là ví dụ semantic encoding. Hình dung hình dáng một vật là ví dụ visual encoding. Chú ý âm của một từ là ví dụ acoustic encoding.
Trong ví dụ giả định, lần đầu gắn nghĩa một thuật ngữ với kiến thức cũ thuộc encoding. Giữ thông tin qua thời gian thuộc storage. Khi được hỏi và nhớ lại định nghĩa đã học, đó là retrieval. Việc không nhớ ra ngay không tự chứng minh thông tin chưa từng được mã hóa.''',
     {'oracle':'concept_table','relations':{'encoding':'input','storage':'retention','retrieval':'return_to_awareness','semantic encoding':'meaning','visual encoding':'images','acoustic encoding':'sounds'}},
     [OS+'psychology-2e/pages/8-1-how-memory-functions'], ordering=False, terms=['encoding','storage','retrieval','semantic encoding','visual encoding','acoustic encoding']),
case('net-final-subnet', 'final', 'Mạng máy tính', 'Phân tích một subnet /27',
     'Tính mask, số bit host, hai biên và dải host hợp lệ từ IPv4/prefix; không nhầm tổng địa chỉ với host.',
'''Với IPv4/prefix /27, còn 5 bit host và có 32 địa chỉ trong khối. Trong ví dụ subnet thông thường này có 30 địa chỉ host dùng được khi loại network và broadcast. Mask của /27 là 255.255.255.224.
Địa chỉ 172.16.8.203/27 thuộc khối 192–223 của octet cuối. Network là 172.16.8.192; broadcast là 172.16.8.223. Dải host dùng được là 172.16.8.193 đến 172.16.8.222. Địa chỉ .203 là một host trong khối này.
Quy trình xác định dải host:
1. Tính số bit host từ prefix đã cho.
2. Tính số địa chỉ trong một khối.
3. Xác định khối chứa địa chỉ IP.
4. Ghi network và broadcast ở hai biên khối.
5. Loại hai biên để ghi dải host dùng được.''',
     {'oracle':'ipv4','input':'172.16.8.203/27'}, [RFC+'rfc4632.html#section-3.1']),
case('calc-final-parts', 'final', 'Vi tích phân', 'Tích phân từng phần',
     'Chọn u và dv, giữ dấu trừ trong integration by parts và áp dụng đúng hai cận của ví dụ.',
'''Công thức integration by parts là integral(u dv)=u*v-integral(v du). Dấu giữa hai phần là dấu trừ. Với tích phân xác định, tích u*v cũng phải được tính tại hai cận.
Ví dụ integral từ 0 đến 1 của x*exp(x) dx: chọn u=x, dv=exp(x)dx, nên du=dx và v=exp(x). Một nguyên hàm là (x-1)*exp(x). Giá trị tại cận 1 là 0, tại cận 0 là -1; tích phân bằng 1. Đạo hàm của (x-1)*exp(x) bằng x*exp(x).
Quy trình giải ví dụ:
1. Chọn u=x và dv=exp(x)dx.
2. Tính du=dx và v=exp(x).
3. Thế vào công thức từng phần có dấu trừ.
4. Rút gọn một nguyên hàm thành (x-1)*exp(x).
5. Lấy giá trị ở cận 1 trừ giá trị ở cận 0.''',
     {'oracle':'parts_exp','bounds':[0,1],'result':1,'antiderivative':'(x-1)*exp(x)','upper_value':0,'lower_value':-1},
     [OS+'calculus-volume-2/pages/3-1-integration-by-parts'], terms=['integration by parts']),
case('psy-final-classical', 'final', 'Tâm lý đại cương', 'Kích thích và phản ứng có điều kiện',
     'Phân biệt NS, UCS, UCR, CS, CR trước và sau học trong ví dụ âm thanh và thức ăn.',
'''Trong ví dụ classical conditioning, thức ăn tự gây tiết nước bọt: thức ăn là unconditioned stimulus (UCS), tiết nước bọt do thức ăn là unconditioned response (UCR). Trước học, âm thanh chưa gắn với thức ăn là neutral stimulus (NS) và chưa gây tiết nước bọt.
Sau khi âm thanh được ghép với thức ăn nhiều lần, âm thanh riêng có thể gây tiết nước bọt. Âm thanh lúc này là conditioned stimulus (CS); tiết nước bọt do âm thanh là conditioned response (CR). Thức ăn không biến thành CS trong ví dụ này.
Trình tự trong ví dụ:
1. Quan sát thức ăn gây tiết nước bọt và âm thanh riêng chưa gây phản ứng đó.
2. Phát âm thanh ngay trước khi cho thức ăn trong nhiều lượt ghép.
3. Thử phát âm thanh riêng sau khi học và quan sát phản ứng tiết nước bọt.''',
     {'oracle':'concept_table','relations':{'UCS':'food','UCR':'salivation_to_food','NS':'sound_before_pairing','CS':'sound_after_pairing','CR':'salivation_to_sound'}},
     [OS+'psychology-2e/pages/6-2-classical-conditioning'], terms=['NS','UCS','UCR','CS','CR']),
case('net-final-routing', 'final', 'Mạng máy tính', 'Chọn tuyến theo longest prefix match',
     'Chọn tuyến khớp có prefix dài nhất, phân biệt đường mặc định và tuyến cụ thể trong bảng đã cho.',
'''Khi nhiều prefix cùng khớp địa chỉ đích, longest prefix match chọn prefix có nhiều bit mạng nhất. Không chọn tuyến chỉ vì prefix ngắn hơn bao phủ nhiều địa chỉ hơn. Tuyến mặc định IPv4 0.0.0.0/0 chỉ được chọn khi không có tuyến khớp cụ thể hơn trong bảng.
Bảng ví dụ có 10.0.0.0/8 qua A, 10.1.0.0/16 qua B, 10.1.2.0/24 qua C và 0.0.0.0/0 qua D. Đích 10.1.2.99 chọn C; 10.1.9.5 chọn B; 10.9.0.4 chọn A; 192.0.2.9 chọn D. Không xét metric khác trong ví dụ này.
Quy trình chọn tuyến trong bảng ví dụ:
1. Liệt kê các prefix trong bảng chứa địa chỉ đích.
2. So sánh độ dài prefix của các tuyến đã khớp.
3. Chọn tuyến khớp có prefix dài nhất.
4. Đọc next hop tương ứng của tuyến vừa chọn.''',
     {'oracle':'longest_prefix','routes':[['10.0.0.0/8','A'],['10.1.0.0/16','B'],['10.1.2.0/24','C'],['0.0.0.0/0','D']],'destinations':{'10.1.2.99':'C','10.1.9.5':'B','10.9.0.4':'A','192.0.2.9':'D'}},
     [RFC+'rfc4632.html#section-5.1'], terms=['longest prefix match','next hop']),
case('calc-final-partial', 'final', 'Vi tích phân', 'Đạo hàm riêng tại một điểm',
     'Giữ biến còn lại như hằng số khi lấy đạo hàm riêng; phân biệt hai đạo hàm và thế điểm sau khi đạo hàm.',
'''Với f(x,y)=x^2*y+3*y^2, đạo hàm riêng theo x coi y là hằng số, nên f_x=2*x*y. Đạo hàm riêng theo y coi x là hằng số, nên f_y=x^2+6*y.
Tại (x,y)=(2,1), f_x=4 và f_y=10. Không thay cả hai biến bằng số trước khi lấy đạo hàm, vì làm vậy biến biểu thức thành hằng số và mất thông tin biến thiên. Hai đạo hàm riêng không mặc nhiên bằng nhau.
Quy trình tính f_x tại (2,1):
1. Chọn x là biến lấy đạo hàm và giữ y như hằng số.
2. Lấy đạo hàm từng hạng để được f_x=2*x*y.
3. Thay x=2 và y=1 vào biểu thức đạo hàm.
4. Tính kết quả số f_x(2,1)=4.''',
     {'oracle':'partial_polynomial','terms':[[1,2,1],[3,0,2]],'point':[2,1],'dx':4,'dy':10,'dx_expression':'2*x*y','dy_expression':'x^2+6*y'},
     [OS+'calculus-volume-3/pages/4-3-partial-derivatives'], terms=['partial derivative']),
case('psy-final-interference', 'final', 'Tâm lý đại cương', 'Hai hướng nhiễu trí nhớ',
     'Phân biệt proactive và retroactive interference theo hướng tác động giữa thông tin cũ và mới.',
'''Proactive interference xảy ra khi thông tin cũ gây khó nhớ thông tin mới. Retroactive interference xảy ra khi thông tin mới gây khó nhớ thông tin cũ. Cả hai liên quan đến khó truy hồi; không có nghĩa mọi dấu vết trí nhớ bị xóa vĩnh viễn.
Ví dụ giả định: đã quen mã tủ cũ rồi tiếp tục nhớ nhầm mã cũ khi cần mã tủ mới là proactive interference. Sau khi học số máy lẻ mới, khó nhớ lại số máy lẻ cũ là retroactive interference. Hướng cũ→mới và mới→cũ khác nhau.
Retrieval là đưa thông tin đã lưu trở lại nhận thức. Một lần không nhớ ra chưa đủ để kết luận thông tin chưa từng được lưu. Đoạn này phân loại các hiện tượng, không quy định một quy trình thao tác hoặc thứ tự bắt buộc giữa hai loại nhiễu.''',
     {'oracle':'concept_table','relations':{'proactive interference':'old_hinders_new','retroactive interference':'new_hinders_old','retrieval':'return_to_awareness'}},
     [OS+'psychology-2e/pages/8-3-problems-with-memory'], ordering=False, terms=['proactive interference','retroactive interference','retrieval']),
]


def main():
    targets=[HERE/'dev.json',HERE/'final.json',HERE/'freeze.json']
    if any(p.exists() for p in targets):
        raise SystemExit('Dataset already frozen. Do not overwrite a revealed split; create a new version with rationale.')
    hashes={}
    for split in ('dev','final'):
        cases=[c for c in CASES if c['split']==split]
        payload={'version':'three-subject-notes-v1','split':split,'cases':cases}
        raw=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode()
        target=HERE/(split+'.json');target.write_bytes(raw);hashes[target.name]=hashlib.sha256(raw).hexdigest()
    manifest={'version':'three-subject-notes-v1','frozen_at':datetime.now(timezone.utc).isoformat(),
              'split_hashes':hashes,'dev_cases':6,'final_cases':6,'requested_questions_per_case':8,
              'human_reviewed':False,'source_scope':'Original agent notes and new examples; referenced general facts checked, no copied book passage or instructor material.',
              'heldout_definition':'Final sources/labels fixed before dev outputs. No final output used for prompt/code selection. Not unseen by model training or dataset author.',
              'review_requirement':'Agent/rule checks do not replace independent team review or 3-5 real users.'}
    (HERE/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'frozen':hashes,'cases':len(CASES)}))


if __name__=='__main__':main()

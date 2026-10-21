/* Dữ liệu tự biên soạn cho mẫu giao diện; không phải đầu ra AI đọc tài liệu thật. */
window.DEMO_DATA = {
  notice: "Mẫu giao diện · Nội dung minh họa · Chưa nối AI hoặc backend",
  practiceRevision: "practice-illustration-v2",
  document: {
    id: "doc-subnet-illustration-v1",
    title: "Ghi chú minh họa: IP và subnet",
    kind: "text",
    sourcePath: "fixtures/subnet-notes.txt",
    sourceNotice: "Do AI biên soạn cho mẫu giao diện; không phải tài liệu của Huy hoặc giảng viên.",
    subjectSuggested: "Mạng máy tính",
    revision: "illustration-v1"
  },
  sourceLines: [
    {
      id: "src-ip-and-mask",
      locator: "§1. IP address và subnet mask",
      text: "Subnet mask cho biết bit nào thuộc phần mạng (network), bit nào thuộc phần máy (host). IP cần đi cùng subnet mask hoặc prefix để xác định subnet; chỉ nhìn IP thì chưa đủ."
    },
    {
      id: "src-prefix-26",
      locator: "§2. Prefix /26",
      text: "/26 nghĩa là 26 bit đầu thuộc network, còn 32 − 26 = 6 bit host. Subnet mask tương ứng là 255.255.255.192: octet cuối 192 = 11000000₂."
    },
    {
      id: "src-block-size",
      locator: "§2. Prefix /26",
      text: "Có 2⁶ = 64 địa chỉ trong một subnet /26. Mỗi block ở octet cuối rộng 64."
    },
    {
      id: "src-network-example",
      locator: "§3. Ví dụ 192.168.1.70/26",
      text: "Các block ở octet cuối: 0–63, 64–127, 128–191, 192–255. 70 nằm trong block 64–127, nên subnet chứa IP này là 192.168.1.64/26. Network address là 192.168.1.64; các bit host đều bằng 0."
    },
    {
      id: "src-broadcast-example",
      locator: "§3. Ví dụ 192.168.1.70/26",
      text: "Broadcast address là 192.168.1.127; các bit host đều bằng 1."
    },
    {
      id: "src-usable-hosts",
      locator: "§4. Địa chỉ host dùng được của subnet trong ví dụ",
      text: "Hai địa chỉ network và broadcast được dành riêng trong subnet /26 này. Host dùng được: 192.168.1.65 đến 192.168.1.126. Số host dùng được: 2⁶ − 2 = 62."
    },
    {
      id: "src-check-order",
      locator: "§5. Cách tự kiểm tra",
      text: "Đọc prefix → tính số bit host → tìm block chứa IP → xác định network/broadcast → đếm host dùng được. Phân biệt 64 địa chỉ tổng cộng với 62 địa chỉ host dùng được trong ví dụ."
    }
  ],
  outline: [
    {
      id: "unit-ip-mask",
      title: "IP và subnet mask",
      status: "sample-ready",
      objective: "Hiểu vì sao IP cần đi cùng mask; xác định subnet của một IP /26."
    },
    {
      id: "unit-network-broadcast",
      title: "Network và broadcast",
      status: "outline-only",
      objective: "Giải thích hai địa chỉ biên bằng các bit host và luyện thêm ví dụ."
    }
  ],
  lesson: {
    id: "unit-ip-mask",
    title: "IP và subnet mask",
    objective: "Từ 192.168.1.70/26, tìm đúng subnet và số host dùng được.",
    sections: [
      {
        id: "lesson-ip-mask-definition",
        title: "IP là địa chỉ. Mask cho biết ranh giới.",
        text: "IPv4 có 32 bit. Subnet mask chia chúng thành phần network và phần host. Vì vậy, cùng một IP nhưng khác mask có thể thuộc subnet khác nhau.",
        sourceRefs: ["src-ip-and-mask"]
      },
      {
        id: "lesson-prefix-26",
        title: "Đọc /26 từ số bit",
        text: "26 bit cho network, còn 6 bit cho host. Mask là 255.255.255.192. Sáu bit tạo được 2⁶ = 64 địa chỉ, nên mỗi block rộng 64.",
        sourceRefs: ["src-prefix-26", "src-block-size"]
      },
      {
        id: "lesson-usable-hosts",
        title: "Đếm host sau khi tìm hai biên",
        text: "Trong subnet /26 của ví dụ, network và broadcast được dành riêng. Bỏ hai địa chỉ này khỏi 64 địa chỉ tổng cộng: còn 62 host dùng được.",
        sourceRefs: ["src-usable-hosts"]
      }
    ],
    example: {
      ip: "192.168.1.70",
      prefix: 26,
      mask: "255.255.255.192",
      hostBits: 6,
      blockSize: 64,
      network: "192.168.1.64",
      broadcast: "192.168.1.127",
      firstHost: "192.168.1.65",
      lastHost: "192.168.1.126",
      usableHosts: 62,
      steps: [
        { id: "step-host-bits", text: "32 − 26 = 6 bit host → 2⁶ = 64 địa chỉ mỗi block.", sourceRefs: ["src-prefix-26", "src-block-size"] },
        { id: "step-find-block", text: "Octet cuối là 70. Nó nằm trong block 64–127.", sourceRefs: ["src-network-example"] },
        { id: "step-find-boundaries", text: "Network: 192.168.1.64. Broadcast: 192.168.1.127.", sourceRefs: ["src-network-example", "src-broadcast-example"] },
        { id: "step-count-usable", text: "Host dùng được: .65–.126, tổng cộng 64 − 2 = 62.", sourceRefs: ["src-usable-hosts"] }
      ]
    },
    mindmap: [
      { id: "map-ip-mask", label: "IP + mask", description: "IP và mask đi cùng nhau để xác định subnet. Mask chỉ ranh giới network/host.", sourceRefs: ["src-ip-and-mask"] },
      { id: "map-host-bits", label: "6 bit host", description: "/26 dành 26 trong 32 bit cho network; còn 6 bit, tạo được 64 địa chỉ.", sourceRefs: ["src-prefix-26", "src-block-size"] },
      { id: "map-boundaries", label: "Network & broadcast", description: "Với .70/26, block là 64–127. Hai biên là .64 và .127.", sourceRefs: ["src-network-example", "src-broadcast-example"] },
      { id: "map-usable-hosts", label: "62 host dùng được", description: "Bỏ hai địa chỉ biên: 64 − 2 = 62. Dải host là .65–.126.", sourceRefs: ["src-usable-hosts"] }
    ]
  },
  questions: [
    {
      id: "q-network-address-v1",
      type: "mcq",
      unitId: "unit-ip-mask",
      prompt: "Network address của 192.168.1.70/26 là địa chỉ nào?",
      options: [
        { id: "q-network-opt-zero", text: "192.168.1.0" },
        { id: "q-network-opt-64", text: "192.168.1.64" },
        { id: "q-network-opt-70", text: "192.168.1.70" },
        { id: "q-network-opt-127", text: "192.168.1.127" }
      ],
      correctOptionId: "q-network-opt-64",
      explanation: "/26 có block rộng 64. 70 thuộc block 64–127, nên địa chỉ đầu block là network: 192.168.1.64. .70 là IP trong subnet; .127 là broadcast.",
      sourceRefs: ["src-block-size", "src-network-example", "src-broadcast-example"]
    },
    {
      id: "q-usable-hosts-v1",
      type: "cloze",
      unitId: "unit-ip-mask",
      prompt: "Subnet 192.168.1.64/26 trong ví dụ có bao nhiêu địa chỉ host dùng được?",
      acceptedAnswers: ["62"],
      answerDisplay: "62",
      explanation: "Có 6 bit host → 2⁶ = 64 địa chỉ. Trừ network .64 và broadcast .127, còn 62 host dùng được: .65–.126.",
      sourceRefs: ["src-prefix-26", "src-usable-hosts"]
    },
    {
      id: "q-match-boundaries-v2",
      type: "matching",
      unitId: "unit-ip-mask",
      prompt: "Ghép vai trò với địa chỉ tương ứng trong subnet chứa 192.168.1.70/26.",
      left: [
        { id: "network", text: "Network address" },
        { id: "broadcast", text: "Broadcast address" },
        { id: "first-host", text: "Host dùng được đầu tiên" }
      ],
      right: [
        { id: "addr-127", text: "192.168.1.127" },
        { id: "addr-65", text: "192.168.1.65" },
        { id: "addr-64", text: "192.168.1.64" }
      ],
      correctPairs: { network: "addr-64", broadcast: "addr-127", "first-host": "addr-65" },
      explanation: "Block chứa 70 là 64–127. .64 là network, .127 là broadcast; .65 là host dùng được đầu tiên.",
      sourceRefs: ["src-network-example", "src-broadcast-example", "src-usable-hosts"]
    },
    {
      id: "q-order-subnet-v2",
      type: "ordering",
      unitId: "unit-ip-mask",
      prompt: "Sắp xếp các bước tự kiểm tra subnet theo quy trình trong nguồn §5.",
      items: [
        { id: "read-prefix", text: "Đọc prefix" },
        { id: "host-bits", text: "Tính số bit host" },
        { id: "find-block", text: "Tìm block chứa IP" },
        { id: "boundaries", text: "Xác định network và broadcast" },
        { id: "usable", text: "Đếm host dùng được" }
      ],
      initialOrder: ["find-block", "usable", "read-prefix", "boundaries", "host-bits"],
      correctOrder: ["read-prefix", "host-bits", "find-block", "boundaries", "usable"],
      explanation: "Nguồn §5 nêu thứ tự này để tự kiểm tra: prefix → bit host → block → hai biên → host dùng được. Câu này kiểm tra quy trình trong nguồn, không khẳng định mọi cách giải khác đều sai.",
      sourceRefs: ["src-check-order"]
    },
    {
      id: "q-explain-mask-v2",
      type: "short_answer",
      unitId: "unit-ip-mask",
      prompt: "Vì sao chỉ có IP address thì chưa đủ xác định subnet? Giải thích trong 1–3 câu.",
      referenceAnswer: "Subnet mask hoặc prefix cho biết ranh giới giữa network và host. Cùng một IP với mask khác nhau có thể thuộc subnet khác nhau, nên cần IP đi cùng mask/prefix để xác định subnet.",
      rubric: ["Nêu vai trò của mask/prefix: chia network và host.", "Giải thích rằng cùng IP với mask khác nhau có thể thuộc subnet khác nhau."],
      explanation: "Đối chiếu ý chính với nguồn §1. Bản mẫu chưa gọi AI chấm tự luận; bạn tự đánh dấu phần đã hiểu hoặc cần ôn.",
      sourceRefs: ["src-ip-and-mask"]
    }
  ],
  cards: [
    { id: "card-prefix-26-v1", front: "IPv4 /26 còn bao nhiêu bit host?", back: "6 bit host, vì 32 − 26 = 6.", sourceRefs: ["src-prefix-26"] },
    { id: "card-network-v1", front: "Network address khác broadcast ở các bit host thế nào?", back: "Network: các bit host bằng 0. Broadcast: các bit host bằng 1.", sourceRefs: ["src-network-example", "src-broadcast-example"] }
  ]
};

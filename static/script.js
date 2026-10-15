const dropzone = document.getElementById("dropzone");
const dropzoneText = document.getElementById("dropzone-text");
const dropzoneSub = document.getElementById("dropzone-sub");
const fileInput = document.getElementById("file-input");
const predictBtn = document.getElementById("predict-btn");
const predictBtnLabel = document.getElementById("predict-btn-label");
const predictBtnRing = document.getElementById("predict-btn-ring");

// em dash(—)가 폰트에 따라 주변 글씨보다 살짝 아래로 처져 보이는 걸 보정하는
// span(style.css의 .em-dash). 대시가 들어가는 문구마다 리터럴 "—" 대신 이걸 쓴다.
const EM_DASH = '<span class="em-dash">—</span>';

// Predict 버튼 테두리를 따라 도는 "기차". 마우스를 올렸을 때만 보이고, 페이드
// 없이 즉시 나타난다(빛줄기가 서서히 나타나는 형식 아님). 속도는 항상 일정해야
// 하므로 conic-gradient(각도 기준 — 알약처럼 길쭉한 모양에서 속도가 불균일해
// 보임) 대신 SVG stroke-dasharray(pathLength=100 = 둘레를 100으로 통일)를
// 쓴다 — 실제 이동 거리 기준이라 직선/모서리 어디든 항상 같은 속도다.
//
// 진행 방향(경로)을 따라 색이 바뀐다 — 시작/꼬리는 흰색에 가깝고 중간은
// 보라색인 대칭 그라데이션. 아주 얇은 조각을 촘촘히 이어 붙여서 자연스럽게
// 색이 변하는 것처럼 보이게 한다. 둘레의 85%를 차지하고, 앞코/꼬리는 round
// linecap으로 둥글게 마무리한다.
const PREDICT_BTN_RING_NS = "http://www.w3.org/2000/svg";
const PREDICT_BTN_RING_ARC = 88; // 둘레의 88%

function predictBtnRingColorAt(from, to, t) {
  const mix = (a, b) => Math.round(a + (b - a) * t);
  const [r1, g1, b1] = from;
  const [r2, g2, b2] = to;
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}

// <rect rx ry>의 pathLength 기반 dash 계산은 브라우저마다 둥근 사각형의
// 실제 둘레 길이를 살짝 다르게(부정확하게) 근사하는 경우가 있고, 이 오차가
// rx/크기가 서로 다른 도형(1번 vs 2번 기차, 반지름이 다름)마다 다르게 나타나서
// 시작점은 맞아도 끝으로 갈수록(특히 모서리를 지난 뒤) 미묘하게 어긋나 보였다.
// <path>는 SVG에서 가장 기본적이고 호(arc-length) 계산이 가장 정확한 도형이라,
// 같은 모양을 <path>로 직접 그려서 이 오차를 없앤다.
//
// 모서리는 원호(A 명령) 대신 3차 베지어(C 명령)로 그리되, 핸들 길이는 원을
// 근사하는 표준값(0.5523)을 그대로 쓴다 — 이 값보다 키우면("더 부드럽게"
// 보이려고 시도했던 것) 곡선이 실제로는 진짜 원보다 더 네모/각지게 보이는
// 역효과가 있었다(그리고 버튼 자체의 모서리와도 모양이 달라져 버렸다).
// 표준값을 쓰면 진짜 원에 아주 가깝게 그려지므로, border-radius(원)로 그려진
// 버튼 본체와도 모양이 정확히 일치한다.
const SMOOTH_CORNER_K = 0.5523;
function roundedRectPath(x, y, w, h, r) {
  const k = r * SMOOTH_CORNER_K;
  return [
    `M ${x + r} ${y}`,
    `H ${x + w - r}`,
    `C ${x + w - r + k} ${y} ${x + w} ${y + r - k} ${x + w} ${y + r}`,
    `V ${y + h - r}`,
    `C ${x + w} ${y + h - r + k} ${x + w - r + k} ${y + h} ${x + w - r} ${y + h}`,
    `H ${x + r}`,
    `C ${x + r - k} ${y + h} ${x} ${y + h - r + k} ${x} ${y + h - r}`,
    `V ${y + r}`,
    `C ${x} ${y + r - k} ${x + r - k} ${y} ${x + r} ${y}`,
    "Z",
  ].join(" ");
}

// 1번 기차의 조각마다 시작 위치가 달라서 각자 다른 @keyframes가 필요하다 —
// CSS 커스텀 프로퍼티를 calc()에 쓰는 방식은 애니메이션이 아예 재생되지 않는
// 문제가 있었어서, 조각별로 리터럴 값을 가진 @keyframes를 JS로 직접 생성해 넣는다.
const predictBtnRingStyleEl = document.createElement("style");
document.head.appendChild(predictBtnRingStyleEl);

const predictBtnRingRects = [];

// 폭 방향(두께) 위치는 DOM/그리는 순서와 무관하게 항상 같아야 하므로(1번이
// 버튼에 더 가깝고, 2번이 그 바깥) 고정 상수로 미리 정해둔다. 쌓이는 순서
// (앞/뒤로 겹쳐 보이는 순서)는 이 값과 별개로, "누구를 먼저 그리느냐"(DOM에
// 먼저 넣을수록 뒤로 깔린다)로만 정한다 — 버튼이 제일 앞, 그다음 1번 기차,
// 2번 기차가 제일 뒤로 가도록 2번을 먼저 그리고 1번을 나중에 그린다.
const PREDICT_BTN_TRAIN1_WIDTH = 3;
const PREDICT_BTN_TRAIN2_WIDTH = 9;
const PREDICT_BTN_TRAIN1_INNER_EDGE = 0;
const PREDICT_BTN_TRAIN2_INNER_EDGE = PREDICT_BTN_TRAIN1_WIDTH;

// --- 2번 기차: 바깥, 1번보다 훨씬 넓은 "하나의" 띠. 제일 뒤로 가도록 1번보다
// 먼저 그린다(DOM에 먼저 들어간 요소가 나중 것보다 아래로 깔린다). ---
// 여러 겹의 얇은 링을 쌓아서 계단식으로 색을 바꾸는 방식은 절대 쓰지 않는다
// (끊어진 여러 겹의 기차처럼 보이고, 각 겹의 round cap이 너무 작아서 뭉치면
// 사선으로 보였다). 대신 딱 2가지 도형만 쓴다:
//   1) 바탕(base): 2번 기차의 전체 폭(넓은 하나의 띠) — 이게 "기차의 몸체"이고
//      캡도 이 하나의 굵은 획 기준이라 크고 뚜렷하게 둥글다.
//   2) 안쪽 악센트(accent): 1번 기차와 맞닿는 가장자리에서 가장 진하고, 버튼에서
//      멀어질수록(바깥쪽) blur로 부드럽게 풀려서 점점 밝아지는 여러 겹의 얇은
//      조각 — 층이 진 게 아니라 안개처럼 번지는 하나의 연속된 그라데이션으로
//      보이게 한다.
// 1번과 완전히 같은 85% 구간·같은 dashoffset 애니메이션을 공유해서 시작/끝
// 위치가 항상 1번과 동일하게 맞물려 돈다.
const PREDICT_BTN_TRAIN2_BASE_COLOR = "rgb(250, 248, 254)";
const PREDICT_BTN_TRAIN2_ACCENT_COLOR = [196, 181, 253];
const PREDICT_BTN_TRAIN2_BASE_RGB = [250, 248, 254];
// 2번 기차는 1번보다 두꺼워서(폭 9px vs 3px) round cap의 반지름도 더 크다 —
// 둘이 같은 지점에서 시작해도 2번의 더 큰 둥근 캡이 1번의 더 작은 캡보다
// 살짝 더 앞으로/뒤로 삐져나와서, 1번에 가려지지 않고 살짝 비쳐 보였다.
// 2번의 양 끝을 아주 살짝 안쪽으로 당겨서(트림) 1번 뒤에 완전히 숨도록 한다 —
// 몸통(보이기 시작하는 부분부터 그 뒤)은 그대로 두고 끝부분만 깎는다.
const PREDICT_BTN_TRAIN2_TRIM = 1.4;
const PREDICT_BTN_TRAIN2_DASHARRAY = `${PREDICT_BTN_RING_ARC - PREDICT_BTN_TRAIN2_TRIM * 2} ${100 - (PREDICT_BTN_RING_ARC - PREDICT_BTN_TRAIN2_TRIM * 2)}`;
const PREDICT_BTN_TRAIN2_DASHOFFSET = -PREDICT_BTN_TRAIN2_TRIM;
// 시작 지점이 0이 아니라 -TRIM만큼 밀렸으니, 목표 지점도 같은 만큼 밀어줘야
// (그냥 -100이 아니라 -TRIM-100) 한 바퀴에 이동하는 총 거리가 1번 기차와 똑같이
// 100이 되어 속도가 계속 맞물린다(안 그러면 조금씩 느려져서 서서히 어긋난다).
predictBtnRingStyleEl.sheet.insertRule(
  `@keyframes predict-btn-train2-spin-trimmed { to { stroke-dashoffset: ${PREDICT_BTN_TRAIN2_DASHOFFSET - 100}; } }`,
  predictBtnRingStyleEl.sheet.cssRules.length
);

// 1번 기차처럼 2번 기차도 "시작/꼬리는 흰색"이어야 한다 — 2번의 바탕(base)은
// 이미 거의 흰색이니, 보라색 악센트를 양 끝에서 안쪽으로 당겨서(위의 캡-숨김용
// 트림보다 훨씬 크게) 그 구간에는 바탕의 흰빛만 남도록 한다. 모든 악센트 겹이
// 똑같은 지점에서 한꺼번에 뚝 끊기면 각지게 보이므로, 겹마다 트림 양을 다르게
// 줘서(가장 진한 안쪽 겹은 많이 당기고, 가장 옅은 바깥쪽 겹은 덜 당김) 여러
// 겹이 서로 다른 지점에서 순서대로 사라지며 자연스럽게 이어지도록 한다.
const PREDICT_BTN_TRAIN2_ACCENT_TRIM_MAX = 15; // 가장 진한(안쪽) 겹 — 가장 일찍 사라짐
const PREDICT_BTN_TRAIN2_ACCENT_TRIM_MIN = 5; // 가장 옅은(바깥쪽) 겹 — 가장 늦게 사라짐
{
  const base = document.createElementNS(PREDICT_BTN_RING_NS, "path");
  base.setAttribute("fill", "none");
  base.setAttribute("pathLength", "100");
  base.setAttribute("stroke-linecap", "round");
  base.setAttribute("stroke-dasharray", PREDICT_BTN_TRAIN2_DASHARRAY);
  base.setAttribute("stroke-dashoffset", String(PREDICT_BTN_TRAIN2_DASHOFFSET));
  base.setAttribute("stroke-width", PREDICT_BTN_TRAIN2_WIDTH);
  base.setAttribute("stroke", PREDICT_BTN_TRAIN2_BASE_COLOR);
  base.style.animation = "predict-btn-train2-spin-trimmed 2.4s linear infinite";
  base.classList.add("predict-btn-ring-el");
  predictBtnRing.appendChild(base);
  predictBtnRingRects.push({ el: base, innerEdge: PREDICT_BTN_TRAIN2_INNER_EDGE, ringWidth: PREDICT_BTN_TRAIN2_WIDTH });

  // 가장 진한 색은 딱 1번 기차와 맞닿는 안쪽 가장자리(폭=0 지점)에만 두고,
  // 버튼에서 멀어질수록(바깥쪽) 점점 밝아져야 한다 — 중앙이 가장 진해지면 안
  // 된다. 하나의 blur로는 진한 지점이 항상 도형 "중심"에 생기므로, 아주 얇은
  // 악센트 여러 개를 안쪽 가장자리부터 바깥으로 점점 밝은 색으로 겹쳐 쌓고
  // 전부 blur로 풀어서, 안쪽 가장자리가 제일 진하고 바깥으로 갈수록 단조롭게
  // 밝아지는 하나의 연속된 번짐처럼 보이게 한다(기차의 몸체/캡은 위 base가
  // 전담하므로, 이 얇은 조각들의 캡 모양은 신경 쓰지 않아도 된다).
  const accentSteps = 5;
  const accentSpan = 4.8; // 이 범위 안에서만 악센트를 겹치고, 나머지는 base의 옅은 색이 그대로 보인다
  for (let i = 0; i < accentSteps; i++) {
    const stepWidth = accentSpan / accentSteps;
    const stepInnerEdge = PREDICT_BTN_TRAIN2_INNER_EDGE + i * stepWidth * 0.55; // 겹치게 배치
    const t = i / (accentSteps - 1);
    const mix = (a, b) => Math.round(a + (b - a) * t);
    const color = `rgb(${mix(PREDICT_BTN_TRAIN2_ACCENT_COLOR[0], PREDICT_BTN_TRAIN2_BASE_RGB[0])}, ${mix(PREDICT_BTN_TRAIN2_ACCENT_COLOR[1], PREDICT_BTN_TRAIN2_BASE_RGB[1])}, ${mix(PREDICT_BTN_TRAIN2_ACCENT_COLOR[2], PREDICT_BTN_TRAIN2_BASE_RGB[2])})`;

    // 겹마다 다른 트림: 진한 겹(t 작음)일수록 많이 당겨서 먼저 사라지고,
    // 옅은 겹(t 큼)일수록 덜 당겨서 늦게 사라진다 — 여러 겹이 순서대로
    // 사라지며 겹치는 구간이 부드러운 계단식(사실상 연속) 페이드를 만든다.
    const trim = PREDICT_BTN_TRAIN2_ACCENT_TRIM_MAX + (PREDICT_BTN_TRAIN2_ACCENT_TRIM_MIN - PREDICT_BTN_TRAIN2_ACCENT_TRIM_MAX) * t;
    const dasharray = `${PREDICT_BTN_RING_ARC - trim * 2} ${100 - (PREDICT_BTN_RING_ARC - trim * 2)}`;
    const dashoffset = -trim;
    const keyframeName = `predict-btn-train2-accent-spin-${i}`;
    predictBtnRingStyleEl.sheet.insertRule(
      `@keyframes ${keyframeName} { to { stroke-dashoffset: ${dashoffset - 100}; } }`,
      predictBtnRingStyleEl.sheet.cssRules.length
    );

    const accent = document.createElementNS(PREDICT_BTN_RING_NS, "path");
    accent.setAttribute("fill", "none");
    accent.setAttribute("pathLength", "100");
    accent.setAttribute("stroke-linecap", "round");
    accent.setAttribute("stroke-dasharray", dasharray);
    accent.setAttribute("stroke-dashoffset", String(dashoffset));
    accent.setAttribute("stroke-width", stepWidth * 1.8);
    accent.setAttribute("stroke", color);
    accent.setAttribute("stroke-opacity", String(1 - t * 0.7));
    accent.setAttribute("filter", "url(#predict-btn-train2-blur)");
    accent.style.animation = `${keyframeName} 2.4s linear infinite`;
    accent.classList.add("predict-btn-ring-el");
    predictBtnRing.appendChild(accent);
    predictBtnRingRects.push({ el: accent, innerEdge: stepInnerEdge, ringWidth: stepWidth });
  }
}

// --- 1번 기차: 안쪽, 경로 방향 그라데이션(흰색 -> 보라 -> 흰색). 2번보다 나중에
// 그려서 2번 위(앞)에 겹쳐 보이게 한다. ---
const PREDICT_BTN_TRAIN1_SEGMENTS = 70; // 촘촘하게 쪼개서 색 변화를 매끄럽게
// 시작/꼬리: 흰색에 가깝지만 완전한 흰색(255,255,255)은 아니다 — 호버 시
// 버튼 배경도 흰색이라, 완전히 같은 흰색이면 기차 끝(라운드 캡)과 남은 15%
// 빈 구간(안 그려진 채 흰 버튼면이 비치는 곳)의 경계가 안 보여서 마치 빈
// 구간까지 기차인 것처럼 보인다. 살짝 연보라 톤을 남겨 경계가 보이게 한다.
const PREDICT_BTN_TRAIN1_EDGE = [253, 252, 255];
// 중간(가장 진한 색): 활성화 전 버튼 배경, 활성화 후 "Predict" 글자색과 완전히
// 똑같은 --accent(#4f46e5) 값을 그대로 쓴다 — 세 군데가 전부 같은 색이어야
// 하므로 더 이상 따로 보정하지 않는다.
const PREDICT_BTN_TRAIN1_CENTER = [79, 70, 229];
{
  const segLen = PREDICT_BTN_RING_ARC / PREDICT_BTN_TRAIN1_SEGMENTS;
  for (let j = 0; j < PREDICT_BTN_TRAIN1_SEGMENTS; j++) {
    const rect = document.createElementNS(PREDICT_BTN_RING_NS, "path");
    rect.setAttribute("fill", "none");
    rect.setAttribute("pathLength", "100");
    rect.setAttribute("stroke-linecap", "round");
    rect.setAttribute("stroke-dasharray", `${segLen} ${100 - segLen}`);
    const startOffset = -(j * segLen);
    rect.setAttribute("stroke-dashoffset", startOffset);
    rect.setAttribute("stroke-width", PREDICT_BTN_TRAIN1_WIDTH);

    // 대칭 램프: 양 끝(j=0, j=N-1)은 흰색, 정중앙은 보라색.
    const p = j / Math.max(PREDICT_BTN_TRAIN1_SEGMENTS - 1, 1);
    const distFromCenter = Math.abs(p - 0.5) * 2; // 0(중앙) ~ 1(양 끝)
    rect.setAttribute("stroke", predictBtnRingColorAt(
      PREDICT_BTN_TRAIN1_CENTER,
      PREDICT_BTN_TRAIN1_EDGE,
      distFromCenter
    ));

    const keyframeName = `predict-btn-train1-seg-${j}`;
    predictBtnRingStyleEl.sheet.insertRule(
      `@keyframes ${keyframeName} { to { stroke-dashoffset: ${startOffset - 100}; } }`,
      predictBtnRingStyleEl.sheet.cssRules.length
    );
    rect.style.animation = `${keyframeName} 2.4s linear infinite`;

    rect.classList.add("predict-btn-ring-el");
    predictBtnRing.appendChild(rect);
    predictBtnRingRects.push({ el: rect, innerEdge: PREDICT_BTN_TRAIN1_INNER_EDGE, ringWidth: PREDICT_BTN_TRAIN1_WIDTH });
  }
}

const PREDICT_BTN_RING_BAND_WIDTH = PREDICT_BTN_TRAIN1_WIDTH + PREDICT_BTN_TRAIN2_WIDTH;
const PREDICT_BTN_RING_REACH = PREDICT_BTN_RING_BAND_WIDTH + 1;

function syncPredictBtnRing() {
  const box = predictBtn.getBoundingClientRect();
  const w = box.width;
  const h = box.height;
  if (!w || !h) return;

  const radius = parseFloat(getComputedStyle(predictBtn).borderRadius) || h / 2;
  const reach = PREDICT_BTN_RING_REACH;
  const outerW = w + reach * 2;
  const outerH = h + reach * 2;

  predictBtnRing.setAttribute("width", outerW);
  predictBtnRing.setAttribute("height", outerH);
  predictBtnRing.setAttribute("viewBox", `0 0 ${outerW} ${outerH}`);
  predictBtnRing.style.left = `-${reach}px`;
  predictBtnRing.style.top = `-${reach}px`;

  predictBtnRingRects.forEach(({ el, innerEdge, ringWidth }) => {
    // 가장 안쪽(1번 기차)의 안쪽 가장자리가 버튼 테두리에 딱 맞닿고, 그 다음부터는
    // 바로 앞 겹의 바깥쪽에 이어 붙는다.
    const offset = innerEdge + ringWidth / 2;
    const inset = reach - offset;
    const x = inset;
    const y = inset;
    const rectW = outerW - inset * 2;
    const rectH = outerH - inset * 2;
    const r = radius + offset;
    el.setAttribute("d", roundedRectPath(x, y, rectW, rectH, r));
  });
}

syncPredictBtnRing();
window.addEventListener("resize", syncPredictBtnRing);
window.addEventListener("load", syncPredictBtnRing);

const alertOverlay = document.getElementById("alert-overlay");
const alertMessage = document.getElementById("alert-message");
const alertOk = document.getElementById("alert-ok");

// 브라우저 기본 alert()는 "127.0.0.1:5000 내용:" 같은 주소 표시줄 문구를 항상
// 붙이기 때문에, 메시지만 깔끔하게 보여주는 커스텀 팝업을 대신 쓴다.
function showAlert(message) {
  alertMessage.textContent = message;
  alertOverlay.hidden = false;
}

function hideAlert() {
  alertOverlay.hidden = true;
}

alertOk.addEventListener("click", hideAlert);
alertOverlay.addEventListener("click", (e) => {
  if (e.target === alertOverlay) hideAlert();
});

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// 서버가 만들어 보내는 안내 문구(파싱 실패 메시지, Read-across 이유 등)는
// escapeHtml로 이스케이프한 뒤 그 안의 em dash(—)만 EM_DASH(보정된 span)로
// 바꿔치기한다 — "—" 자체는 HTML 특수문자가 아니라 escapeHtml이 건드리지
// 않으므로 안전하게 치환할 수 있다.
function escapeHtmlWithDash(str) {
  return escapeHtml(str).replaceAll("—", EM_DASH);
}

// training 화합물 이름을 클릭하면 그 화합물의 등록된 구조를 그려서 보여준다.
// 예측 응답마다 미리 5개씩 이미지를 다 실어보내지 않고, 실제로 클릭했을 때만
// /api/structure_image로 요청해서(같은 SMILES는 캐시해서 재요청 안 함) 보여준다.
const structureOverlay = document.getElementById("structure-overlay");
const structureName = document.getElementById("structure-name");
const structureImage = document.getElementById("structure-image");
const structureMw = document.getElementById("structure-mw");
const structureError = document.getElementById("structure-error");
const structureClose = document.getElementById("structure-close");
const structureDataCache = new Map();

function hideStructure() {
  structureOverlay.hidden = true;
}

function renderStructureData(data) {
  structureImage.src = `data:image/png;base64,${data.image_base64}`;
  structureImage.hidden = false;
  structureMw.innerHTML = `<span class="label-en">MW</span> ${data.molecular_weight}`;
  structureMw.hidden = false;
}

async function showStructure(name, smiles) {
  structureName.textContent = stripStereoNote(name);
  structureImage.hidden = true;
  structureMw.hidden = true;
  structureError.hidden = true;
  structureOverlay.hidden = false;

  if (structureDataCache.has(smiles)) {
    renderStructureData(structureDataCache.get(smiles));
    return;
  }

  try {
    const res = await fetch(`/api/structure_image?smiles=${encodeURIComponent(smiles)}`);
    const data = await res.json();
    if (!res.ok || !data.image_base64) {
      throw new Error(data.error || "구조를 불러오지 못했습니다.");
    }
    structureDataCache.set(smiles, data);
    renderStructureData(data);
  } catch (err) {
    structureError.textContent = `구조를 불러오지 못했습니다: ${err.message || err}`;
    structureError.hidden = false;
  }
}

structureClose.addEventListener("click", hideStructure);
structureOverlay.addEventListener("click", (e) => {
  if (e.target === structureOverlay) hideStructure();
});

// "전체 6,241개 기준 예측 보러가기" 팝업 — subset_retrain일 때 같이 계산해둔
// mol.global_predictions를 버튼의 data 속성에 그대로 실어뒀다가(추가 요청 없음),
// 클릭하면 구조 팝업과 같은 형태의 모달로 보여준다.
const globalPredOverlay = document.getElementById("global-pred-overlay");
const globalPredBody = document.getElementById("global-pred-body");
const globalPredClose = document.getElementById("global-pred-close");

function hideGlobalPred() {
  globalPredOverlay.hidden = true;
}

function showGlobalPred(predictions) {
  const entries = Object.values(predictions || {});
  globalPredBody.innerHTML = entries.length
    ? entries
        .map((p) => {
          const cls = p.predicted_class === "BBB+" ? "pred-pos" : "pred-neg";
          const pct = (p.probability * 100).toFixed(1);
          return `<tr><td>${p.label}</td><td class="${cls}">${p.predicted_class}</td><td>${pct}%</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="3">예측 모델이 없습니다.</td></tr>`;
  globalPredOverlay.hidden = false;
}

globalPredClose.addEventListener("click", hideGlobalPred);
globalPredOverlay.addEventListener("click", (e) => {
  if (e.target === globalPredOverlay) hideGlobalPred();
});

document.getElementById("results").addEventListener("click", (e) => {
  const globalBtn = e.target.closest(".global-pred-link");
  if (globalBtn) {
    showGlobalPred(JSON.parse(globalBtn.dataset.globalPredictions || "{}"));
    return;
  }

  const btn = e.target.closest(".compound-name-btn");
  if (!btn) return;
  showStructure(btn.dataset.name || "", btn.dataset.smiles || "");
});

const statusMsg = document.getElementById("status-msg");
const resultsEl = document.getElementById("results");
const predictForm = document.getElementById("predict-form");
const smilesInput = document.getElementById("smiles-input");

function formatCompoundName(name) {
  return name.replace(/\([^)]*입체정보 없음[^)]*\)/g, (m) => `<span class="stereo-note">${m}</span>`);
}

// 요약 테이블의 초록색 식별 배지는 짧게 유지: 입체정보 누락 안내는 상세보기 제목에서
// 이미 보여주므로 여기서는 뺀다.
function stripStereoNote(name) {
  return name.replace(/\s*\([^)]*입체정보 없음[^)]*\)/g, "");
}

// 한글/영어가 섞인 문장에서 영어(및 붙은 숫자) 부분만 감싸서, 폰트가 같아도 서로
// 다르게 보이는 굵기를 CSS로 따로 보정할 수 있게 한다.
function balanceEnKoWeight(text) {
  return text.replace(/[A-Za-z][A-Za-z0-9]*/g, (m) => `<span class="label-en">${m}</span>`);
}

const DESCRIPTOR_LABELS = {
  molecular_weight: "분자량 (MW)",
  logp: "LogP",
  tpsa: "TPSA (Å²)",
  hbd: "수소결합 공여체 (HBD)",
  hba: "수소결합 수용체 (HBA)",
  rotatable_bonds: "회전 가능 결합 수",
  num_rings: "고리 수",
  num_atoms: "원자 수",
};

let selectedFile = null;

function updatePredictBtn() {
  // 입력이 비어 있어도 버튼은 계속 눌러볼 수 있게 두고, 실제로 눌렀을 때
  // predictForm의 submit 핸들러에서 안내 팝업을 띄운다(로딩 중이 아니면 항상 활성).
  predictBtn.disabled = false;
}

function setSelectedFile(file) {
  selectedFile = file;
  if (file) {
    dropzoneText.textContent = `선택된 파일: ${file.name}`;
    dropzoneSub.textContent = "다시 클릭해서 다른 파일 선택";
  } else {
    dropzoneText.innerHTML = '파일을 끌어다 놓거나 <span class="drop-browse">찾아보기</span>';
    dropzoneSub.textContent = "MOL, SDF 파일 · 최대 5MB";
  }
  updatePredictBtn();
}

fileInput.addEventListener("change", () => {
  setSelectedFile(fileInput.files[0] || null);
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    setSelectedFile(file);
  }
});

function setStatus(text, kind) {
  statusMsg.textContent = text;
  statusMsg.className = kind || "";
}

// 파일 업로드와 SMILES 직접 입력은 서로 다른 엔드포인트(/api/upload,
// /api/predict_smiles)를 쓰므로, 둘 다 입력돼 있으면 두 요청을 동시에 보내고
// 결과 화합물 목록을 하나로 합쳐서 보여준다. 한쪽만 입력돼 있으면 그 하나만 보낸다.
async function submitRequest(fetchPromises) {
  resultsEl.innerHTML = "";
  predictBtn.disabled = true;
  predictBtn.classList.add("is-loading");
  predictBtnLabel.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

  try {
    const responses = await Promise.all(fetchPromises);
    const dataList = await Promise.all(responses.map((res) => res.json()));

    let molecules = [];
    const errors = [];
    responses.forEach((res, i) => {
      if (res.ok) {
        molecules = molecules.concat(dataList[i].molecules);
      } else {
        errors.push(dataList[i].error || "알 수 없는 오류가 발생했습니다.");
      }
    });

    renderResults(molecules);
    setStatus(errors.join(" / "), errors.length ? "error" : "");
  } catch (err) {
    setStatus(`요청 중 오류가 발생했습니다: ${err}`, "error");
  } finally {
    predictBtn.classList.remove("is-loading");
    predictBtnLabel.textContent = "Predict";
    updatePredictBtn();
  }
}

const smilesPlaceholder = document.getElementById("smiles-placeholder");
function syncSmilesPlaceholder() {
  smilesPlaceholder.hidden = smilesInput.value.length > 0;
}
smilesInput.addEventListener("input", () => {
  updatePredictBtn();
  syncSmilesPlaceholder();
});
syncSmilesPlaceholder();

predictForm.addEventListener("submit", (e) => {
  e.preventDefault();

  const smiles = smilesInput.value.trim();
  if (!selectedFile && !smiles) {
    showAlert("구조를 업로드하거나 SMILES Code를 입력하세요.");
    return;
  }

  const requests = [];
  if (selectedFile) {
    const formData = new FormData();
    formData.append("file", selectedFile);
    requests.push(fetch("/api/upload", { method: "POST", body: formData }));
  }
  if (smiles) {
    requests.push(
      fetch("/api/predict_smiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ smiles }),
      })
    );
  }

  submitRequest(requests);
});

function renderResults(molecules) {
  resultsEl.innerHTML = "";
  if (molecules.length === 0) return;

  const wrap = document.createElement("div");
  wrap.className = "compare-wrap";

  const table = document.createElement("table");
  table.className = "compare-table";
  table.innerHTML = `<tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  molecules.forEach((mol, i) => {
    const num = i + 1;

    if (!mol.valid) {
      const tr = document.createElement("tr");
      tr.className = "compare-row invalid";
      tr.innerHTML = `<td><span class="row-num">${num}</span></td><td colspan="3">${mol.error}</td>`;
      tbody.appendChild(tr);
      return;
    }

    const entries = Object.values(mol.predictions || {});
    const ad = mol.applicability_domain;
    const mode = mol.prediction_mode;

    let predBadges;
    if (mode === "none") {
      predBadges = `<span class="predictions-empty">필수 Moiety 일치 Training 화합물 없음 ${EM_DASH} 예측 생략</span>`;
    } else if (mode === "read_across") {
      const ra = computeReadAcross(ad);
      const pct = (ra.fraction * 100).toFixed(0);
      const verdict = ra.predictedClass
        ? `<span class="${ra.predictedClass === "BBB+" ? "pred-pos" : "pred-neg"}">${ra.predictedClass}</span>`
        : "동률";
      predBadges = `<span class="mini-badge">Read-across: ${verdict} (${pct}%)</span>`;
    } else if (entries.length === 0) {
      predBadges = `<span class="predictions-empty">모델 없음</span>`;
    } else {
      predBadges = entries
        .map((p) => {
          const cls = p.predicted_class === "BBB+" ? "pred-pos" : "pred-neg";
          const pct = (p.probability * 100).toFixed(0);
          return `<span class="mini-badge">${p.label}: <span class="${cls}">${p.predicted_class} ${pct}%</span></span>`;
        })
        .join("");
    }

    const adText = !ad ? "정보 없음" : ad.within_domain ? "높음" : "낮음";

    const row = document.createElement("tr");
    row.className = "compare-row";
    row.innerHTML = `
      <td><span class="row-num">${num}</span></td>
      <td>
        <img class="thumb" src="data:image/png;base64,${mol.image_base64}" alt="${mol.name}">
        ${mol.identified_name ? `<div class="identified-name">✓ ${stripStereoNote(mol.identified_name)}</div>` : ""}
      </td>
      <td>
        <div class="mini-badge-row">${predBadges}</div>
        ${mode === "none" ? "" : `<div class="ad-inline">신뢰도: ${adText}</div>`}
      </td>
      <td><button type="button" class="row-toggle">상세 ▾</button></td>`;

    const rows = Object.entries(mol.descriptors)
      .map(([key, val]) => `<tr><td>${DESCRIPTOR_LABELS[key] || key}</td><td>${val}</td></tr>`)
      .join("");

    const detailRow = document.createElement("tr");
    detailRow.className = "detail-row";
    detailRow.hidden = true;
    detailRow.innerHTML = `
      <td colspan="4">
        <div class="detail-panel">
          <h3 class="detail-title">${formatCompoundName(mol.name)}</h3>
          <div class="detail-top">
            <div class="detail-left">
              <img class="detail-image" src="data:image/png;base64,${mol.image_base64}" alt="${mol.name}">
            </div>
            <div class="detail-right">
              <h4 class="section-title"><span class="title-en">Molecular Descriptors</span> <span class="title-kr">(주요 물성 정보)</span></h4>
              <table class="descriptor-table">${rows}</table>
            </div>
          </div>
          <div class="detail-full">
            ${renderPredictions(mol)}
          </div>
          <div class="detail-full">
            ${renderApplicabilityDomain(mol.applicability_domain)}
          </div>
        </div>
      </td>`;

    const toggleBtn = row.querySelector(".row-toggle");
    toggleBtn.addEventListener("click", () => {
      detailRow.hidden = !detailRow.hidden;
      toggleBtn.textContent = detailRow.hidden ? "상세 ▾" : "닫기 ▴";
    });

    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  });

  wrap.appendChild(table);
  resultsEl.appendChild(wrap);
}

function renderApplicabilityDomain(ad) {
  if (!ad) {
    return `<p class="predictions-empty">신뢰도 정보 없음 (ml/build_ad_index.py 실행 필요).</p>`;
  }

  const pct = (ad.max_similarity * 100).toFixed(1);
  const statusText = ad.within_domain ? "신뢰도 높음" : "신뢰도 낮음";
  const similarityLabel = "가장 가까운 Top 3 training 화합물과의 구조 유사도 (Fingerprint 기반)";
  const similarityMethodNote = "※ 99% 이상 일치하는 화합물이 있을 경우 해당 화합물과의 유사도를 그대로 반영";

  const neighborRows = ad.nearest_training_compounds
    .map(
      (n) => `
      <tr>
        <td><button type="button" class="compound-name-btn" data-smiles="${escapeHtml(n.smiles)}" data-name="${escapeHtml(n.compound_name)}">${formatCompoundName(n.compound_name)}</button></td>
        <td class="${n.experimental_label === "BBB+" ? "pred-pos" : "pred-neg"}">${n.experimental_label} <span class="exp-tag">experimental</span></td>
        <td>${(n.similarity * 100).toFixed(1)}%</td>
      </tr>`
    )
    .join("");

  // SMILES에 "..."로 필수 Moiety를 지정했을 때만 보이는 안내 — 오류(SMARTS
  // 해석 실패)/일치하는 training 화합물이 0개인 경우는 테이블 자체가 없으니
  // 상단에 경고 박스로 보여준다. 정상적으로 몇 개로 좁혀졌는지는 별도 박스 없이
  // 바로 아래 "기준 임계값 ..., training 화합물 N개 기준" 줄의 N 자체를 그
  // 매칭 개수로 바꿔서 보여준다(필터가 없으면 그대로 전체 6,241개).
  let substructureNotice = "";
  let trainingCountText = `Training 화합물 ${ad.n_training_compounds.toLocaleString()}개 기준`;
  if (ad.required_substructure_smarts) {
    if (ad.substructure_error) {
      substructureNotice = `<p class="substructure-notice substructure-error">${escapeHtmlWithDash(ad.substructure_error)}</p>`;
    } else if (ad.substructure_match_count === 0) {
      substructureNotice = `<p class="substructure-notice substructure-error">지정한 필수 Moiety <code>"${escapeHtml(ad.required_substructure_smarts)}"</code>를 포함하는 Training 화합물이 없습니다.</p>`;
    } else {
      trainingCountText = `필수 Moiety <code>"${escapeHtml(ad.required_substructure_smarts)}"</code>를 포함하는 Training 화합물 ${ad.substructure_match_count.toLocaleString()}개 기준`;
    }
  }

  if (ad.nearest_training_compounds.length === 0) {
    return `
      <div class="ad-section">
        <h4 class="section-title"><span class="title-en">Applicability Domain</span> <span class="title-kr">(예측 신뢰도 ${EM_DASH} 구조 유사도 기반)</span></h4>
        ${substructureNotice}
      </div>`;
  }

  return `
    <div class="ad-section">
      <h4 class="section-title"><span class="title-en">Applicability Domain</span> <span class="title-kr">(예측 신뢰도 ${EM_DASH} 구조 유사도 기반)</span></h4>
      ${substructureNotice}
      <div class="ad-status-row">
        <div class="status-tag">${statusText}</div>
        <div class="similarity-stat">
          <div class="similarity-value">${pct}%</div>
          <div class="similarity-text">
            <div class="similarity-label">${balanceEnKoWeight(similarityLabel)}</div>
            <div class="similarity-method-note">${similarityMethodNote}</div>
            <div class="similarity-meta">${trainingCountText} (학습 데이터셋: B3DB)</div>
          </div>
        </div>
      </div>
      <h5 class="section-subtitle">Nearest training compounds <span class="subtitle-kr">(실험/문헌 라벨 ${EM_DASH} 예측값 아님)</span></h5>
      <div class="table-scroll">
        <table class="neighbor-table">
          <thead><tr><th>Training 화합물</th><th>실험 라벨</th><th>Similarity</th></tr></thead>
          <tbody>${neighborRows}</tbody>
        </table>
      </div>
    </div>`;
}

// 필수 Moiety로 매칭된 training 화합물 수가 즉석 재학습하기엔 너무 적거나(또는
// 한쪽 라벨로 치우쳐) read-across 모드일 때, 그 매칭된 화합물들(ad.nearest_training_compounds,
// 이미 구조 유사도 기준 상위 몇 개로 좁혀져 있음)의 실험 라벨을 유사도로 가중 평균해서
// "판정"을 만든다. 모델이 뭔가를 학습한 게 아니라, 제일 비슷한 기존 화합물들의 실제
// 실험값을 그대로 참고하는 것뿐이다.
function computeReadAcross(ad) {
  const compounds = (ad && ad.nearest_training_compounds) || [];
  let posWeight = 0;
  let totalWeight = 0;
  compounds.forEach((n) => {
    const w = n.similarity;
    totalWeight += w;
    if (n.experimental_label === "BBB+") posWeight += w;
  });
  const fraction = totalWeight > 0 ? posWeight / totalWeight : 0.5;
  const predictedClass = fraction > 0.5 ? "BBB+" : fraction < 0.5 ? "BBB-" : null;
  return { fraction, predictedClass, n: compounds.length };
}

function renderPredictions(mol) {
  const predictions = mol.predictions;
  const ad = mol.applicability_domain;
  const mode = mol.prediction_mode;

  // 필수 Moiety를 포함하는 training 화합물이 0개 — 비교할 근거가 전혀 없으므로
  // 예측 자체를 생략하고 그 이유를 명시한다(단순 "신뢰도 낮음" 경고보다 강한 조치).
  if (mode === "none") {
    return `
      <div class="predictions">
        <h4 class="section-title"><span class="title-en">BBB Prediction</span> <span class="title-kr">(모델별 예측값 ${EM_DASH} 실험값 아님)</span></h4>
        <p class="substructure-notice substructure-error">Training 화합물이 없어 예측을 생략합니다 ${EM_DASH} 비교할 근거가 전혀 없는 수치를 보여주지 않기 위함.</p>
      </div>`;
  }

  // 매칭된 화합물이 재학습하기엔 너무 적거나(또는 라벨이 한쪽으로 치우쳐) 모델 학습
  // 자체가 불안정/불가능한 경우 — read-across(가장 가까운 화합물들의 실험 라벨을
  // 유사도로 가중 평균)로 대체한다.
  if (mode === "read_across") {
    const ra = computeReadAcross(ad);
    const pct = (ra.fraction * 100).toFixed(1);
    const verdict = ra.predictedClass
      ? `<span class="${ra.predictedClass === "BBB+" ? "pred-pos" : "pred-neg"}">${ra.predictedClass}</span>`
      : "판정 불명확(동률)";
    return `
      <div class="predictions">
        <h4 class="section-title"><span class="title-en">BBB Prediction</span> <span class="title-kr">(모델별 예측값 ${EM_DASH} 실험값 아님)</span></h4>
        <div class="low-confidence-banner">
          <p>Read-across 판정: ${verdict} (매칭 화합물 ${ra.n}개의 실험 라벨을 구조 유사도로 가중 평균 ${EM_DASH} BBB+ 비중 ${pct}%)</p>
          <p class="read-across-reason read-across-divider">${escapeHtmlWithDash(mol.read_across_reason || "")}</p>
          <p class="read-across-reason">${escapeHtmlWithDash(mol.read_across_detail || "")}
            <button type="button" class="global-pred-link" data-global-predictions="${escapeHtml(JSON.stringify(mol.global_predictions || {}))}">전체 6,241개 기준 예측 보러가기</button>
          </p>
        </div>
      </div>`;
  }

  if (!predictions || Object.keys(predictions).length === 0) {
    return `<p class="predictions-empty">학습된 예측 모델이 없습니다 (ml/train.py 실행 필요).</p>`;
  }

  const subsetNote =
    mode === "subset_retrain" && mol.retrain_info
      ? `<div class="low-confidence-banner">
          <p>필수 Moiety를 포함하는 Training 화합물 ${mol.retrain_info.n_compounds}개(BBB+ ${mol.retrain_info.n_positive}개 / BBB- ${mol.retrain_info.n_negative}개)만으로 모델을 즉석 재학습한 결과입니다.</p>
          <p>전체 6,241개 기준 예측과 다를 수 있습니다.
            <button type="button" class="global-pred-link" data-global-predictions="${escapeHtml(JSON.stringify(mol.global_predictions || {}))}">전체 6,241개 기준 예측 보러가기</button>
          </p>
        </div>`
      : "";

  const lowConfidence = mode === "global" && ad && !ad.within_domain;

  const entries = Object.values(predictions); // {label, probability, predicted_class}

  const classes = new Set(entries.map((p) => p.predicted_class));
  const agreementCell =
    classes.size === 1
      ? `<span class="${[...classes][0] === "BBB+" ? "pred-pos" : "pred-neg"}">${[...classes][0]}</span> 일치`
      : `불일치`;

  const rows = entries
    .map((p, i) => {
      const pct = (p.probability * 100).toFixed(1);
      const cls = p.predicted_class === "BBB+" ? "pred-pos" : "pred-neg";
      return `
        <tr>
          <td>${p.label}</td>
          <td class="${cls}">${p.predicted_class}</td>
          <td>
            <div class="prob-bar-track">
              <div class="prob-bar-fill ${cls}" style="width:${pct}%"></div>
            </div>
            <span class="prob-value">${pct}%</span>
          </td>
          ${i === 0 ? `<td class="agree-cell" rowspan="${entries.length}">${agreementCell}</td>` : ""}
        </tr>`;
    })
    .join("");

  return `
    <div class="predictions">
      <h4 class="section-title"><span class="title-en">BBB Prediction</span> <span class="title-kr">(모델별 예측값 ${EM_DASH} 실험값 아님)</span></h4>
      <table class="prediction-table">
        <thead><tr><th>Model used</th><th>Prediction</th><th>Probability</th><th>일치여부</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${subsetNote}
      ${lowConfidence
        ? `<p class="low-confidence-banner">⚠ 신뢰도 낮음 ${EM_DASH} 위 확률은 training chemical space에서 많이 벗어난 구조에 대한 추정치이므로 참고용으로만 활용할 것.</p>`
        : ""
      }
    </div>`;
}

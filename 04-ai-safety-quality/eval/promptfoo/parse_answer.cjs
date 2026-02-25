module.exports = (response) => {
  // response 可能是：
  // 1) 已解析 object: { job_id, status, answer, ... }
  // 2) string(JSON): '{"job_id":...}'
  // 3) object with raw string: { raw: '{"job_id":...}' }
  // 4) object with nested response fields (provider wrappers)

  const tryParseJson = (s) => {
    if (typeof s !== 'string') return null;
    const t = s.trim();
    if (!t) return null;
    // 只在看起來像 JSON 時才 parse，避免 "key: value" 之類炸掉
    if (!(t.startsWith('{') || t.startsWith('['))) return null;
    try { return JSON.parse(t); } catch { return null; }
  };

  const unwrap = (x) => {
    // 常見 wrapper 欄位：output / result / response / raw
    if (!x) return x;
    if (typeof x === 'string') {
      return tryParseJson(x) ?? x;
    }
    if (typeof x === 'object') {
      // 若已經有 answer 了，直接用
      if (typeof x.answer === 'string') return x;

      // 先處理 raw
      if (typeof x.raw === 'string') {
        const inner = tryParseJson(x.raw);
        if (inner) return inner;
      }

      // 常見包裝欄位逐個拆
      for (const k of ['output', 'result', 'response', 'data']) {
        if (x[k]) {
          const y = unwrap(x[k]);
          if (y) return y;
        }
      }
      return x;
    }
    return x;
  };

  const obj = unwrap(response);

  // 最終取 answer
  if (obj && typeof obj === 'object' && typeof obj.answer === 'string') {
    return obj.answer;
  }

  // 若是純字串，直接回傳（至少不會 No output）
  if (typeof obj === 'string') return obj;

  // 其他情況：轉字串
  try { return JSON.stringify(obj); } catch { return String(obj); }
};

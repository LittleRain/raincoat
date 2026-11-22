export function reviewWindows(duration, step = 8, context = 2) {
  if (!Number.isFinite(duration) || duration <= 0 || step <= 0 || context < 0) return [];
  const windows = [];
  for (let start = 0; start < duration; start += step) {
    windows.push({ start, end: Math.min(duration, start + step + context) });
  }
  return windows;
}

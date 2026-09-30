// In-memory rate limiter. Resets on cold start and is per-instance only,
// so it is a best-effort deterrent, not a hard guarantee.

const WINDOW_MS = 60 * 60 * 1000; // 1 hour
const MAX_REQUESTS_PER_WINDOW = 5;
const MAX_REQUESTS_PER_DAY = 15;
const DAY_MS = 24 * 60 * 60 * 1000;

type Bucket = { hourTimestamps: number[]; dayTimestamps: number[] };

const buckets = new Map<string, Bucket>();

export function checkRateLimit(ip: string): { allowed: boolean; retryAfterMs?: number } {
  const now = Date.now();
  let bucket = buckets.get(ip);
  if (!bucket) {
    bucket = { hourTimestamps: [], dayTimestamps: [] };
    buckets.set(ip, bucket);
  }

  bucket.hourTimestamps = bucket.hourTimestamps.filter((t) => now - t < WINDOW_MS);
  bucket.dayTimestamps = bucket.dayTimestamps.filter((t) => now - t < DAY_MS);

  if (bucket.hourTimestamps.length >= MAX_REQUESTS_PER_WINDOW) {
    const oldest = bucket.hourTimestamps[0];
    return { allowed: false, retryAfterMs: WINDOW_MS - (now - oldest) };
  }
  if (bucket.dayTimestamps.length >= MAX_REQUESTS_PER_DAY) {
    const oldest = bucket.dayTimestamps[0];
    return { allowed: false, retryAfterMs: DAY_MS - (now - oldest) };
  }

  bucket.hourTimestamps.push(now);
  bucket.dayTimestamps.push(now);
  return { allowed: true };
}

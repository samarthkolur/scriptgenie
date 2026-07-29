/**
 * Reading the API's RFC 9457 problem documents.
 *
 * The API answers every failure with the same shape, so the client parses one
 * format. What matters on this side is not being fooled by the ones it is not
 * given: a proxy timing out returns HTML, a network failure returns nothing at
 * all, and a client that assumes a JSON body will throw a `SyntaxError` that
 * tells the user nothing about what went wrong.
 */

/** The members the API guarantees on every problem document. */
export type Problem = {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly detail: string;
  readonly instance?: string;
  readonly requestId?: string;
  /** Error-specific members, e.g. the conflicts that blocked a generation. */
  readonly extra: Readonly<Record<string, unknown>>;
};

export class ApiError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }

  get status(): number {
    return this.problem.status;
  }

  /**
   * Whether this is the caller's session having lapsed rather than a fault.
   * The UI's response to it is to sign in again, not to show an error.
   */
  get isUnauthenticated(): boolean {
    return this.problem.status === 401;
  }
}

const KNOWN_MEMBERS = new Set([
  "type",
  "title",
  "status",
  "detail",
  "instance",
  "request_id",
]);

/**
 * Turn a failed response into a `Problem`, whatever the body turned out to be.
 *
 * Never throws. This runs on the error path, and an error handler that fails
 * replaces a diagnosable problem with an undiagnosable one.
 */
export async function toProblem(response: Response): Promise<Problem> {
  let body: unknown = undefined;
  try {
    body = await response.json();
  } catch {
    // Not JSON: a proxy error page, an empty body, a truncated response.
  }

  if (body === null || typeof body !== "object") {
    return {
      type: "about:blank",
      title: response.statusText || "Request failed",
      status: response.status,
      detail: `The API returned ${response.status} with an unreadable body.`,
      extra: {},
    };
  }

  const record = body as Record<string, unknown>;
  const extra: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    if (!KNOWN_MEMBERS.has(key)) extra[key] = value;
  }

  return {
    type: asString(record.type) ?? "about:blank",
    title: asString(record.title) ?? response.statusText ?? "Request failed",
    status: typeof record.status === "number" ? record.status : response.status,
    detail: asString(record.detail) ?? `The API returned ${response.status}.`,
    ...(asString(record.instance) !== undefined
      ? { instance: asString(record.instance) as string }
      : {}),
    ...(asString(record.request_id) !== undefined
      ? { requestId: asString(record.request_id) as string }
      : {}),
    extra,
  };
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

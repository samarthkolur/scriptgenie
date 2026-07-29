import { describe, expect, it } from "vitest";

import { ApiError, toProblem } from "@/lib/api/problem";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

describe("toProblem", () => {
  it("reads a well-formed problem document", async () => {
    const problem = await toProblem(
      jsonResponse(404, {
        type: "https://scriptgenie.app/problems/not-found",
        title: "Not found",
        status: 404,
        detail: "no such project",
        instance: "/v1/projects/42",
        request_id: "trace-7",
      }),
    );

    expect(problem.type).toBe("https://scriptgenie.app/problems/not-found");
    expect(problem.detail).toBe("no such project");
    expect(problem.requestId).toBe("trace-7");
  });

  it("collects error-specific members separately", async () => {
    const problem = await toProblem(
      jsonResponse(409, {
        type: "https://scriptgenie.app/problems/conflict-state",
        title: "Request conflicts with the current state",
        status: 409,
        detail: "an unresolved HARD conflict blocks generation",
        conflicts: [{ rule_id: "horror_comedy_tonal_pressure" }],
      }),
    );

    expect(problem.extra.conflicts).toEqual([
      { rule_id: "horror_comedy_tonal_pressure" },
    ]);
    // The standard members are not duplicated into `extra`, so a caller
    // iterating it sees only what is specific to this error.
    expect(problem.extra.title).toBeUndefined();
  });

  it("survives a body that is not JSON at all", async () => {
    // What a proxy or load balancer returns when it gives up on the upstream.
    const response = new Response(
      "<html><body>504 Gateway Timeout</body></html>",
      {
        status: 504,
        statusText: "Gateway Timeout",
      },
    );

    const problem = await toProblem(response);

    expect(problem.status).toBe(504);
    expect(problem.title).toBe("Gateway Timeout");
    expect(problem.detail).toContain("unreadable body");
  });

  it("survives an empty body", async () => {
    const problem = await toProblem(new Response(null, { status: 502 }));

    expect(problem.status).toBe(502);
    expect(problem.detail).toContain("unreadable body");
  });

  it("survives a JSON body that is not an object", async () => {
    const problem = await toProblem(jsonResponse(500, "something went wrong"));

    expect(problem.status).toBe(500);
    expect(problem.type).toBe("about:blank");
  });

  it("falls back to the response status when the body disagrees in type", async () => {
    const problem = await toProblem(
      jsonResponse(400, { status: "four hundred", detail: 12 }),
    );

    expect(problem.status).toBe(400);
    expect(problem.detail).toContain("400");
  });
});

describe("ApiError", () => {
  it("carries the problem and reads as its detail", async () => {
    const error = new ApiError(
      await toProblem(
        jsonResponse(401, {
          type: "https://scriptgenie.app/problems/unauthenticated",
          title: "Authentication required",
          status: 401,
          detail: "this endpoint requires a bearer access token",
        }),
      ),
    );

    expect(error.message).toBe("this endpoint requires a bearer access token");
    expect(error.status).toBe(401);
    expect(error.isUnauthenticated).toBe(true);
  });

  it("distinguishes a lapsed session from an actual fault", async () => {
    const error = new ApiError(
      await toProblem(jsonResponse(500, { detail: "internal" })),
    );

    // The UI's answer to 401 is to sign in again; to 500 it is to report a
    // fault. Conflating them tells the user to sign in when signing in will
    // not help.
    expect(error.isUnauthenticated).toBe(false);
  });
});

import { render } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SessionSync,
  shouldResync,
} from "@/components/features/auth/session-sync";

type Listener = (
  event: string,
  session: { user: { id: string } } | null,
) => void;

const mocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  listener: undefined as Listener | undefined,
  unsubscribe: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mocks.refresh }),
}));

vi.mock("@/lib/supabase/client", () => ({
  browserClient: () => ({
    auth: {
      onAuthStateChange(listener: Listener) {
        mocks.listener = listener;
        return {
          data: { subscription: { unsubscribe: mocks.unsubscribe } },
        };
      },
    },
  }),
}));

/** Drive the Supabase callback the way the client would. */
function emit(event: string, userId: string | null): void {
  act(() => {
    mocks.listener?.(event, userId === null ? null : { user: { id: userId } });
  });
}

beforeEach(() => {
  mocks.refresh.mockClear();
  mocks.unsubscribe.mockClear();
  mocks.listener = undefined;
});

describe("shouldResync", () => {
  it("is false while the server and browser agree", () => {
    expect(shouldResync("user-1", "user-1")).toBe(false);
    expect(shouldResync(null, null)).toBe(false);
  });

  it("is true when the session ended after the page was rendered", () => {
    expect(shouldResync("user-1", null)).toBe(true);
  });

  it("is true when a different user now holds the session", () => {
    // Signing in as someone else in another tab leaves this tab rendering the
    // first user's projects behind the second user's session.
    expect(shouldResync("user-1", "user-2")).toBe(true);
  });

  it("is true when the browser signed in against a page rendered for nobody", () => {
    expect(shouldResync(null, "user-1")).toBe(true);
  });
});

describe("SessionSync", () => {
  it("renders nothing", () => {
    const { container } = render(<SessionSync userId="user-1" />);

    expect(container.innerHTML).toBe("");
  });

  it("refreshes when the session ends in another tab", () => {
    render(<SessionSync userId="user-1" />);

    emit("SIGNED_OUT", null);

    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh on an hourly token refresh", () => {
    render(<SessionSync userId="user-1" />);

    // TOKEN_REFRESHED fires roughly every hour and changes nothing the server
    // rendered. Refreshing on it would re-run every Server Component, and on a
    // long-lived tab that is a page reload the user did not ask for.
    emit("TOKEN_REFRESHED", "user-1");

    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it("does not refresh on the initial session it was rendered for", () => {
    render(<SessionSync userId="user-1" />);

    emit("INITIAL_SESSION", "user-1");

    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it("refreshes at most once while the server keeps disagreeing", () => {
    render(<SessionSync userId="user-1" />);

    // A server that still accepts the cookie would re-render the same identity,
    // and refreshing on every subsequent event would spin the page.
    emit("SIGNED_OUT", null);
    emit("SIGNED_OUT", null);
    emit("INITIAL_SESSION", null);

    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it("acts again once the identity changes to a new one", () => {
    render(<SessionSync userId="user-1" />);

    emit("SIGNED_OUT", null);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);

    emit("SIGNED_IN", "user-2");
    expect(mocks.refresh).toHaveBeenCalledTimes(2);
  });

  it("re-arms after the server re-renders with the new identity", () => {
    const { rerender } = render(<SessionSync userId="user-1" />);

    emit("SIGNED_OUT", null);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);

    // The refresh landed: the server now agrees nobody is signed in.
    rerender(<SessionSync userId={null} />);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);

    // A later sign-in is a fresh mismatch and must be acted on.
    emit("SIGNED_IN", "user-3");
    expect(mocks.refresh).toHaveBeenCalledTimes(2);
  });

  it("unsubscribes on unmount", () => {
    const { unmount } = render(<SessionSync userId="user-1" />);

    unmount();

    // Every mount attaches a listener to the memoised client; leaking them
    // means an old tree's router.refresh() runs on a page it no longer owns.
    expect(mocks.unsubscribe).toHaveBeenCalledTimes(1);
  });
});

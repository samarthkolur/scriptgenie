"use client";

import { useEffect, useRef, useState } from "react";

import { detectConflictsAction } from "@/app/app/projects/[projectId]/actions";
import type { ConflictReport, ConstraintBundle } from "@/lib/api-client";
import {
  bundleFormSchema,
  toBundle,
  type BundleFormValues,
} from "@/lib/constraints/schema";

/**
 * How long the answers have to stop changing before they are judged.
 *
 * Long enough that dragging through a select does not fire once per option,
 * short enough that a writer who changes a certificate and looks down at the
 * panel finds the new verdict already there. Detection is deterministic and
 * costs no model quota, so the number is chosen for the writer's attention
 * rather than to protect a budget.
 */
export const DETECT_DEBOUNCE_MS = 350;

export type ConflictState = {
  /** The last report received, kept while a newer one is in flight. */
  readonly report: ConflictReport | null;
  /**
   * When that report was produced.
   *
   * A verdict is only meaningful alongside the knowledge base version and the
   * moment it was reached: the same answers judged by a later version may come
   * back differently, and a writer looking at a stale panel deserves to be
   * able to tell. Taken when the response lands rather than sent by the API,
   * which has no reason to carry a clock the client already has.
   */
  readonly judgedAt: Date | null;
  readonly pending: boolean;
  readonly error: string | null;
  /** True when the answers on screen are not the ones `report` judged. */
  readonly stale: boolean;
};

/**
 * Keep a conflict report in step with the wizard's answers.
 *
 * Four things this deliberately does not do:
 *
 * It does not clear the previous report while fetching the next. A panel that
 * empties on every keystroke reads as "no conflicts" for a few hundred
 * milliseconds, which is the one wrong answer it must never give; `stale` says
 * so instead, and the caller keeps the gate closed on the old verdict until
 * the new one lands.
 *
 * It does not send a half-filled form. The API would answer 422 and the writer
 * would see a transport error where they had simply not finished — so a bundle
 * is submitted only once the schema accepts it.
 *
 * It does not trust the order responses come back in. Every request carries a
 * sequence number and anything but the newest is dropped, because a slow reply
 * to an abandoned edit would otherwise overwrite the verdict on the current
 * one.
 *
 * It does not store `pending` or `error`. Both are functions of which answers
 * have an outcome yet, so deriving them keeps them from disagreeing with the
 * report — and it is what makes a failure clear itself the moment the writer
 * changes something, rather than leaving a stale red line under answers that
 * have since moved on.
 */
export function useConflictReport(values: BundleFormValues): ConflictState {
  const parsed = bundleFormSchema.safeParse(values);
  /**
   * The request body, serialised — and so also the identity of the answers.
   * Using the payload itself as the effect's dependency is what makes "the
   * report is for the current answers" a comparison rather than a belief.
   */
  const key: string | null = parsed.success
    ? JSON.stringify(toBundle(parsed.data))
    : null;

  const [judged, setJudged] = useState<{
    readonly key: string;
    readonly report: ConflictReport;
    readonly at: Date;
  } | null>(null);
  const [failed, setFailed] = useState<{
    readonly key: string;
    readonly message: string;
  } | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    // Nothing to ask about, already answered, or already refused: an outcome
    // for these exact answers exists, so asking again would only re-run a
    // deterministic function over the same inputs.
    if (key === null || judged?.key === key || failed?.key === key) return;

    const current = ++sequence.current;
    const timer = setTimeout(() => {
      const bundle = JSON.parse(key) as ConstraintBundle;
      void detectConflictsAction(bundle).then((result) => {
        if (current !== sequence.current) return;
        if (result.ok) setJudged({ key, report: result.data, at: new Date() });
        else setFailed({ key, message: result.error });
      });
    }, DETECT_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [key, judged?.key, failed?.key]);

  return {
    report: judged?.report ?? null,
    judgedAt: judged?.at ?? null,
    pending: key !== null && judged?.key !== key && failed?.key !== key,
    error: failed !== null && failed.key === key ? failed.message : null,
    stale: judged === null || judged.key !== key,
  };
}

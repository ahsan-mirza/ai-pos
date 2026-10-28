import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { normalizeStoreName, storeNameError } from "./validation";
import { availabilityBlocksSubmit, useAvailabilityCheck } from "./useAvailabilityCheck";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => {};
  let reject: (error: unknown) => void = () => {};
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const validEmail = (value: string) => value.includes("@") && value.includes(".");

describe("store names", () => {
  it("collapses whitespace and rejects an empty or one-character name", () => {
    expect(normalizeStoreName("  Al   Noor  ")).toBe("Al Noor");
    expect(storeNameError("", true)).toBe("Enter a store name.");
    expect(storeNameError("  A  ")).toBe("Enter a store name.");
    expect(storeNameError("Al Noor")).toBeUndefined();
  });
});

describe("useAvailabilityCheck", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces keystrokes and checks the normalized value once", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async (value: string) => ({ available: value === "sara@example.com" }));
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) =>
        useAvailabilityCheck({
          value,
          debounceMs: 500,
          isValid: validEmail,
          normalize: (next) => next.trim().toLowerCase(),
          check,
        }),
      { initialProps: { value: "" } },
    );

    rerender({ value: "s" });
    rerender({ value: "sara@" });
    rerender({ value: " Sara@Example.com " });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(check).not.toHaveBeenCalled();
    expect(result.current.status).toBe("idle");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(check).toHaveBeenCalledTimes(1);
    expect(check).toHaveBeenCalledWith("sara@example.com", expect.any(AbortSignal));
    expect(result.current.status).toBe("available");
  });

  it("does not ask again for the same normalized value", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async () => ({ available: true }));
    const { rerender } = renderHook(
      ({ value }: { value: string }) =>
        useAvailabilityCheck({
          value,
          debounceMs: 500,
          isValid: validEmail,
          normalize: (next) => next.trim().toLowerCase(),
          check,
        }),
      { initialProps: { value: "sara@example.com" } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    rerender({ value: "Sara@Example.com" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("aborts the previous request when the value or country key changes", async () => {
    vi.useFakeTimers();
    const signals: AbortSignal[] = [];
    const pending: Deferred<{ available: boolean }>[] = [];
    const check = vi.fn((_value: string, signal: AbortSignal) => {
      signals.push(signal);
      const next = deferred<{ available: boolean }>();
      pending.push(next);
      return next.promise;
    });
    const { rerender } = renderHook(
      ({ value, contextKey }: { value: string; contextKey: string }) =>
        useAvailabilityCheck({
          value,
          contextKey,
          debounceMs: 500,
          isValid: () => true,
          normalize: (next) => next,
          check,
        }),
      { initialProps: { value: "+971501234567", contextKey: "AE" } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    rerender({ value: "+971501234567", contextKey: "SA" });
    expect(signals[0]?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(check).toHaveBeenCalledTimes(2);
    expect(signals[1]?.aborted).toBe(false);
  });

  it("ignores a stale response after the value changes", async () => {
    vi.useFakeTimers();
    const first = deferred<{ available: boolean }>();
    const check = vi.fn((value: string) => {
      if (value === "old@example.com") return first.promise;
      return Promise.resolve({ available: false });
    });
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) =>
        useAvailabilityCheck({
          value,
          debounceMs: 500,
          isValid: validEmail,
          normalize: (next) => next,
          check,
        }),
      { initialProps: { value: "old@example.com" } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    rerender({ value: "new@example.com" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.status).toBe("unavailable");
    await act(async () => {
      first.resolve({ available: true });
    });
    expect(result.current.status).toBe("unavailable");
    expect(result.current.result).toEqual({ available: false });
  });

  it("keeps a network failure off the available state and retries", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async () => {
      throw new Error("offline");
    });
    const { result } = renderHook(() =>
      useAvailabilityCheck({
        value: "sara@example.com",
        debounceMs: 500,
        isValid: validEmail,
        normalize: (next) => next,
        check,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.status).toBe("error");
    expect(result.current.result).toBeNull();
    check.mockResolvedValueOnce({ available: true });
    act(() => {
      result.current.retry();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(check).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("available");
  });

  it("cancels a pending check on unmount", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async () => ({ available: true }));
    const { unmount } = renderHook(() =>
      useAvailabilityCheck({
        value: "sara@example.com",
        debounceMs: 500,
        isValid: validEmail,
        normalize: (next) => next,
        check,
      }),
    );
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(check).not.toHaveBeenCalled();
  });

  it("blocks submit while a valid value is still unchecked or taken", () => {
    expect(availabilityBlocksSubmit("idle", false)).toBe(true);
    expect(availabilityBlocksSubmit("idle", true)).toBe(true);
    expect(availabilityBlocksSubmit("checking", true)).toBe(true);
    expect(availabilityBlocksSubmit("unavailable", true)).toBe(true);
    expect(availabilityBlocksSubmit("available", true)).toBe(false);
    expect(availabilityBlocksSubmit("error", true)).toBe(false);
  });
});

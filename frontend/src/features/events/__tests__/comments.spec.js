import { describe, expect, it } from "vitest";

import { canPost, COMMENT_MAX_LENGTH, hasThread, validateComment } from "@/features/events/comments";

describe("comment rules (SCRUM-61)", () => {
  it("accepts comments from submission until the event closes", () => {
    for (const status of ["submitted", "under_review", "returned", "planning", "confirmed"]) {
      expect(canPost(status)).toBe(true);
    }
    for (const status of ["draft", "rejected", "cancelled", "completed", undefined]) {
      expect(canPost(status)).toBe(false);
    }
  });

  it("has a thread for every status except draft", () => {
    expect(hasThread("draft")).toBe(false);
    expect(hasThread("rejected")).toBe(true);
    expect(hasThread("under_review")).toBe(true);
  });

  it("caps a comment at the API's 1000 characters", () => {
    expect(COMMENT_MAX_LENGTH).toBe(1000);
    expect(validateComment("x".repeat(1000))).toBeNull();
    expect(validateComment("x".repeat(1001))).toBe("Keep it to 1000 characters.");
  });

  it("refuses an empty or whitespace-only comment", () => {
    for (const text of ["", "   ", "\n\t "]) {
      expect(validateComment(text)).toBe("A comment can't be empty.");
    }
  });

  it("measures the trimmed text", () => {
    expect(validateComment(`  ${"x".repeat(1000)}  `)).toBeNull();
  });
});

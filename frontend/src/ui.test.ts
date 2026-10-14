import { describe, expect, it } from "vitest";
import { apiUrl } from "./api/client";
import { cardCover, coverUrl } from "./ui";

describe("cardCover", () => {
  it("uses the painted image for a custom cover that has one", () => {
    expect(cardCover({ id: "s1", cover: "custom", cover_image_version: "v2" })).toBe(apiUrl("scenarios/s1/cover-image?v=v2"));
  });

  it("uses the theme image for a theme cover, painted or not", () => {
    expect(cardCover({ id: "s1", cover: "camp", cover_image_version: "v2" })).toBe(coverUrl("camp"));
  });

  it("falls back to the field theme for a custom cover without an image", () => {
    expect(cardCover({ id: "s1", cover: "custom" })).toBe(coverUrl("field"));
    expect(cardCover({ id: "s1", cover: "custom", cover_image_version: null })).toBe(coverUrl("field"));
  });
});

import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: "https://jangstrading.com/sitemap.xml", // 도메인 구매 후 변경
  };
}

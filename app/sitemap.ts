import type { MetadataRoute } from "next";
import fs from "fs";
import path from "path";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://www.jangstrading.com";
  const now = new Date();

  // 기본 페이지
  const pages: MetadataRoute.Sitemap = [
    { url: baseUrl, lastModified: now, changeFrequency: "daily", priority: 1.0 },
    { url: `${baseUrl}/stocks`, lastModified: now, changeFrequency: "daily", priority: 0.9 },
    { url: `${baseUrl}/sectors`, lastModified: now, changeFrequency: "daily", priority: 0.9 },
    { url: `${baseUrl}/sectors?view=mid`, lastModified: now, changeFrequency: "daily", priority: 0.8 },
    { url: `${baseUrl}/sectors?view=theme`, lastModified: now, changeFrequency: "daily", priority: 0.8 },
    { url: `${baseUrl}/reports`, lastModified: now, changeFrequency: "daily", priority: 0.7 },
  ];

  // 종목별 상세 페이지
  try {
    const dataPath = path.join(process.cwd(), "public", "data", "stock-rankings.json");
    const raw = fs.readFileSync(dataPath, "utf-8");
    const data = JSON.parse(raw);
    for (const stock of data.data || []) {
      if (stock.ticker) {
        pages.push({
          url: `${baseUrl}/stocks/${stock.ticker}`,
          lastModified: now,
          changeFrequency: "daily",
          priority: 0.6,
        });
      }
    }
  } catch (e) {}

  // 섹터/테마 상세 페이지
  try {
    const dataPath = path.join(process.cwd(), "public", "data", "stock-rankings.json");
    const raw = fs.readFileSync(dataPath, "utf-8");
    const data = JSON.parse(raw);
    const sectors = new Set<string>();
    for (const stock of data.data || []) {
      if (stock.sector && stock.sector !== "기타") sectors.add(stock.sector);
      if (stock.sector_mid && stock.sector_mid !== "기타") sectors.add(stock.sector_mid);
    }
    for (const name of sectors) {
      pages.push({
        url: `${baseUrl}/sectors/${encodeURIComponent(name)}`,
        lastModified: now,
        changeFrequency: "daily",
        priority: 0.7,
      });
    }
  } catch (e) {}

  // 테마 페이지
  try {
    const themePath = path.join(process.cwd(), "public", "data", "theme-map.json");
    const raw = fs.readFileSync(themePath, "utf-8");
    const themes = JSON.parse(raw);
    for (const name of Object.keys(themes)) {
      pages.push({
        url: `${baseUrl}/sectors/${encodeURIComponent(name)}`,
        lastModified: now,
        changeFrequency: "daily",
        priority: 0.6,
      });
    }
  } catch (e) {}

  // AI 리포트 페이지
  try {
    const indexPath = path.join(process.cwd(), "public", "data", "reports", "index.json");
    const raw = fs.readFileSync(indexPath, "utf-8");
    const reports = JSON.parse(raw);
    for (const r of reports) {
      pages.push({
        url: `${baseUrl}/reports/${r.date}`,
        lastModified: now,
        changeFrequency: "never",
        priority: 0.5,
      });
    }
  } catch (e) {}

  return pages;
}

"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";

interface Stock {
  name: string;
  ticker: string;
  market: string;
}

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [results, setResults] = useState<Stock[]>([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(-1);
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  // 데이터 로드
  useEffect(() => {
    fetch("/data/stock-rankings.json")
      .then((r) => r.json())
      .then((d) => {
        setStocks(
          d.data
            .filter((s: Stock) => s.ticker)
            .map((s: Stock) => ({ name: s.name, ticker: s.ticker, market: s.market }))
        );
      })
      .catch(() => {});
  }, []);

  // 검색
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    const q = query.trim().toLowerCase();
    const matched = stocks
      .filter((s) => s.name.toLowerCase().includes(q) || s.ticker.includes(q))
      .slice(0, 8);
    setResults(matched);
    setOpen(matched.length > 0);
    setSelected(-1);
  }, [query, stocks]);

  // 바깥 클릭 시 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // 종목 이동
  function goTo(ticker: string) {
    setQuery("");
    setOpen(false);
    router.push(`/stocks/${ticker}`);
  }

  // 키보드
  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && selected >= 0) {
      goTo(results[selected].ticker);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          width="13" height="13" viewBox="0 0 16 16" fill="currentColor"
        >
          <path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z"/>
        </svg>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => query.trim() && results.length > 0 && setOpen(true)}
          onKeyDown={handleKey}
          placeholder="종목명 · 티커 검색"
          className="w-40 sm:w-48 bg-white/[0.06] border border-white/[0.06] rounded-lg pl-8 pr-3 py-1.5 text-[12px] text-white placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-blue)] transition"
        />
      </div>

      {/* 드롭다운 */}
      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-72 bg-[#161b22] border border-white/[0.1] rounded-xl shadow-2xl overflow-hidden z-50">
          {results.map((s, i) => (
            <button
              key={s.ticker}
              onClick={() => goTo(s.ticker)}
              className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition ${
                i === selected ? "bg-white/[0.08]" : "hover:bg-white/[0.04]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-white font-medium">{s.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-md ${
                  s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                }`}>{s.market}</span>
              </div>
              <span className="text-[11px] text-[var(--text-muted)] num">{s.ticker}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

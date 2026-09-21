import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "한 칸 여유 | 지하철 혼잡도",
  description: "노선과 탑승 시간을 선택하고 칸별 혼잡도 추정치를 비교하세요.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

import { useState } from "react";
import type { CalibrationBin } from "../lib/api";
import { useI18n } from "../i18n";
import { num, pct } from "../lib/format";

export interface CalibrationSeries {
  key: string;
  label: string;
  color: string;
  ece: number;
  answers: number;
  bins: CalibrationBin[];
  label_at: { bin: number; dx: number; dy: number; anchor: "start" | "middle" | "end" };
}

const W = 560;
const H = 360;
const PAD = { left: 52, right: 20, top: 16, bottom: 48 };
const TICKS = [0, 0.2, 0.4, 0.6, 0.8, 1];
const SURFACE = "#fdfcfa";
const x = (v: number) => PAD.left + v * (W - PAD.left - PAD.right);
const y = (v: number) => H - PAD.bottom - v * (H - PAD.top - PAD.bottom);

function tooltipPosition(bin: CalibrationBin) {
  const left = x(bin.mean_risk) / W;
  const shift = left < 0.3 ? "-12px" : left > 0.7 ? "calc(-100% + 12px)" : "-50%";
  return { left: `${left * 100}%`, top: `${(y(bin.observed) / H) * 100}%`, transform: `translate(${shift}, calc(-100% - 14px))` };
}

interface Hover {
  series: CalibrationSeries;
  bin: CalibrationBin;
}

export function CalibrationChart({ series }: { series: CalibrationSeries[] }) {
  const [hover, setHover] = useState<Hover | null>(null);
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-3">
      <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-1.5 p-0 text-xs text-fog-300" aria-label={t("calib.legend")}>
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} aria-hidden="true" />
            {t("calib.ece", { label: s.label, v: num(s.ece, 3) })}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <span className="inline-block w-4 border-t border-dashed border-fog-400" aria-hidden="true" />
          {t("calib.perfect")}
        </li>
      </ul>
      <div className="relative" dir="ltr">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={t("calib.aria")}>
          {TICKS.map((t) => (
            <g key={t}>
              <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--color-ink-600)" strokeWidth={1} />
              <text x={x(0) - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--color-fog-400)">{num(t, 1)}</text>
              <text x={x(t)} y={y(0) + 18} textAnchor="middle" fontSize={11} fill="var(--color-fog-400)">{num(t, 1)}</text>
            </g>
          ))}
          <text x={(x(0) + x(1)) / 2} y={H - 8} textAnchor="middle" fontSize={12} fill="var(--color-fog-300)">
            {t("calib.x")}
          </text>
          <text transform={`translate(14 ${(y(0) + y(1)) / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill="var(--color-fog-300)">
            {t("calib.y")}
          </text>
          <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--color-fog-400)" strokeWidth={1.5} strokeDasharray="5 5" />
          {series.map((s) => (
            <g key={s.key}>
              <polyline
                points={s.bins.map((b) => `${x(b.mean_risk)},${y(b.observed)}`).join(" ")}
                fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
              />
              {s.bins.map((b) => (
                <circle key={b.low} cx={x(b.mean_risk)} cy={y(b.observed)} r={4} fill={s.color} stroke={SURFACE} strokeWidth={2} />
              ))}
            </g>
          ))}
          {series.map((s) => {
            const { bin, dx, dy, anchor } = s.label_at;
            const b = s.bins[Math.min(bin, s.bins.length - 1)];
            return (
              <text
                key={`${s.key}-label`} x={x(b.mean_risk) + dx} y={y(b.observed) + dy}
                textAnchor={anchor} fontSize={11} fill="var(--color-fog-200)" stroke={SURFACE} strokeWidth={3} paintOrder="stroke"
              >
                {s.label}
              </text>
            );
          })}
          {series.map((s) =>
            s.bins.map((b) => (
              <circle
                key={`${s.key}-${b.low}-hit`} cx={x(b.mean_risk)} cy={y(b.observed)} r={12} fill="transparent"
                onMouseEnter={() => setHover({ series: s, bin: b })} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover({ series: s, bin: b })} onBlur={() => setHover(null)} tabIndex={0}
                aria-label={t("calib.point", { label: s.label, a: num(b.low, 1), b: num(b.high, 1), m: num(b.mean_risk, 2), o: pct(b.observed), n: num(b.n, 0) })}
              />
            )),
          )}
        </svg>
        {hover && (
          <div
            className="pointer-events-none absolute z-10 min-w-[180px] rounded-lg border border-hair bg-ink-800 px-3 py-2 text-xs text-fog-200 shadow-lg"
            style={tooltipPosition(hover.bin)}
          >
            <div className="mb-1 flex items-center gap-2 text-fog-100">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: hover.series.color }} aria-hidden="true" />
              {hover.series.label}
            </div>
            <div>{t("calib.tipRisk", { a: num(hover.bin.low, 1), b: num(hover.bin.high, 1), m: num(hover.bin.mean_risk, 2) })}</div>
            <div>{t("calib.tipReal", { o: pct(hover.bin.observed) })}</div>
            <div className="text-fog-400">{t("calib.tipN", { n: num(hover.bin.n, 0) })}</div>
          </div>
        )}
      </div>
      <details className="text-xs text-fog-400">
        <summary className="cursor-pointer">{t("calib.table")}</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-start">
            <thead>
              <tr>
                <th className="py-1.5 pe-3 font-normal">{t("calib.band")}</th>
                {series.map((s) => <th key={s.key} className="py-1.5 pe-3 font-normal">{t("calib.col", { label: s.label })}</th>)}
              </tr>
            </thead>
            <tbody className="font-mono text-fog-300">
              {Array.from({ length: 10 }, (_, i) => i / 10).map((low) => (
                <tr key={low} className="border-t border-hair">
                  <td className="py-1.5 pe-3">{t("calib.range", { a: num(low, 1), b: num(low + 0.1, 1) })}</td>
                  {series.map((s) => {
                    const b = s.bins.find((v) => Math.abs(v.low - low) < 1e-9);
                    return <td key={s.key} className="py-1.5 pe-3">{b ? t("calib.cell", { m: num(b.mean_risk, 2), o: pct(b.observed), n: num(b.n, 0) }) : t("calib.none")}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

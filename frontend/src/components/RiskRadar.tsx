type Dim = { key: string; label: string; score: number };
type Props = { dimensions: Dim[]; size?: number; max?: number };

export function RiskRadar({ dimensions, size = 200, max = 100 }: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 32;
  const N = dimensions.length;
  if (N === 0) return null;
  const angle = (i: number) => (Math.PI * 2 * i) / N - Math.PI / 2;

  const pointAt = (i: number, v: number) => {
    const r = (Math.max(0, Math.min(max, v)) / max) * radius;
    return [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))] as const;
  };

  const polygon = dimensions.map((d, i) => pointAt(i, d.score).join(',')).join(' ');
  const gridLevels = max === 100 ? [20, 40, 60, 80, 100] : [2, 4, 6, 8, 10];

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {gridLevels.map(lv => (
        <polygon key={lv}
          points={dimensions.map((_, i) => pointAt(i, lv).join(',')).join(' ')}
          fill="none" stroke="#374151" strokeWidth="0.5" />
      ))}
      {dimensions.map((_, i) => {
        const [x, y] = pointAt(i, max);
        return <line key={`a${i}`} x1={cx} y1={cy} x2={x} y2={y} stroke="#374151" strokeWidth="0.5" />;
      })}
      <polygon points={polygon} fill="#ef4444" fillOpacity="0.20" stroke="#fca5a5" strokeWidth="1.5" />
      {dimensions.map((d, i) => {
        const [x, y] = pointAt(i, d.score);
        return <circle key={`d${i}`} cx={x} cy={y} r="2.5" fill="#fca5a5" />;
      })}
      {dimensions.map((d, i) => {
        const [x, y] = pointAt(i, max * 1.15);
        return (
          <text key={d.key} x={x} y={y} fontSize="10" fill="#9ca3af"
            textAnchor="middle" dominantBaseline="middle">
            {d.label} {d.score.toFixed(0)}
          </text>
        );
      })}
    </svg>
  );
}

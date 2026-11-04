const ROWS = [' ▐▛███▜▌', '▝▜█████▛▘', '  ▘▘ ▝▝'];

const QUADRANTS: Record<string, [number, number, number, number]> = {
  ' ': [0, 0, 0, 0],
  '▐': [0, 1, 0, 1],
  '▌': [1, 0, 1, 0],
  '▛': [1, 1, 1, 0],
  '▜': [1, 1, 0, 1],
  '█': [1, 1, 1, 1],
  '▝': [0, 1, 0, 0],
  '▘': [1, 0, 0, 0],
};

const PIXELS = ROWS.flatMap((row, r) =>
  [...row].flatMap((char, c) =>
    QUADRANTS[char]
      .map((on, q) => (on ? {x: c * 2 + (q % 2), y: r * 2 + (q >> 1)} : null))
      .filter((p): p is {x: number; y: number} => p !== null),
  ),
);

export const Mascot: React.FC<{cell: number; color: string}> = ({cell, color}) => {
  const w = cell * 0.3;
  const h = cell * 0.6;
  const d = PIXELS.map(({x, y}) => `M${x * w} ${y * h}h${w}v${h}h${-w}z`).join('');
  return (
    <svg width={18 * w} height={6 * h} viewBox={`0 0 ${18 * w} ${6 * h}`} style={{display: 'block'}} shapeRendering="crispEdges">
      <path d={d} fill={color} />
    </svg>
  );
};

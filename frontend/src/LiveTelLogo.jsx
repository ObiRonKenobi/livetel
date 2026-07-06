/** Pixel operator icon — cyan #00d4ff on #0a0a0a (matches dashboard background) */
export default function LiveTelLogo({ className = '' }) {
  const C = '#00d4ff'
  const B = '#0a0a0a'
  const px = 16

  const grid = [
    '0000111100000000',
    '0001111111000000',
    '0011111111100000',
    '0111111111110000',
    '0110111111101100',
    '0111111111111100',
    '0111111111111100',
    '0111100000011110',
    '0111100000011110',
    '0111111111111100',
    '0111111111111100',
    '0011111111111000',
    '0011111111111000',
    '0001111111110000',
    '0000111111100000',
    '0000011111000000',
  ]

  const rects = []
  for (let y = 0; y < px; y += 1) {
    for (let x = 0; x < px; x += 1) {
      if (grid[y][x] === '1') {
        rects.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={C} />)
      }
    }
  }

  return (
    <svg
      viewBox={`0 0 ${px} ${px}`}
      xmlns="http://www.w3.org/2000/svg"
      className={`block shrink-0 h-[3.125rem] md:h-[3.625rem] w-[3.125rem] md:w-[3.625rem] ${className}`}
      aria-hidden
      style={{ imageRendering: 'pixelated' }}
    >
      <rect width={px} height={px} fill={B} />
      {rects}
      <rect x={4} y={7} width={3} height={2} fill={B} />
      <rect x={9} y={7} width={3} height={2} fill={B} />
      <rect x={7} y={7} width={2} height={1} fill={B} />
      <rect x={7} y={2} width={2} height={1} fill={B} />
    </svg>
  )
}

/** LiveTel pixel logo — cyan #00d4ff on #0a0a0a */
export default function LiveTelLogo({ size = 48, className = '' }) {
  return (
    <img
      src="/livetel-logo.png"
      width={size}
      height={size}
      alt=""
      className={`shrink-0 ${className}`}
      style={{ imageRendering: 'pixelated' }}
      draggable={false}
    />
  )
}

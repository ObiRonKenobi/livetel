/** Header logo — PNG in /public, black bg + LiveTel cyan */
export default function LiveTelLogo({ className = '' }) {
  return (
    <img
      src="/livetel-logo.png"
      alt=""
      className={`block shrink-0 h-[3.125rem] md:h-[3.625rem] w-[3.125rem] md:w-[3.625rem] object-contain ${className}`}
      style={{ imageRendering: 'pixelated' }}
      draggable={false}
    />
  )
}

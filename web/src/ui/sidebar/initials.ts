/** Up to two capital letters from a name: "Camila Ortega" -> "CO", "ana.ruiz" -> "AR", "fraud_ops" -> "FO". */
export function initials(name: string): string {
  const parts = name.split(/[\s._-]+/u).filter(Boolean)
  if (parts.length === 0) return ''
  const letters = parts.length === 1 ? [...parts[0]].slice(0, 2) : [parts[0], parts[parts.length - 1]].map((part) => [...part][0])
  return letters.join('').toLocaleUpperCase()
}

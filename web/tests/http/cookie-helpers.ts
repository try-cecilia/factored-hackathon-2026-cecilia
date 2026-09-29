/** The Set-Cookie line for `suffix`, with or without the __Host- prefix. */
export const cookieNamed = (lines: string[], suffix: string) => lines.find((c) => new RegExp(`^(__Host-)?${suffix}=[^;]`).test(c))

/** The attributes of a Set-Cookie line, lowercased: `httponly`, `secure`, `samesite=lax`... */
export const flags = (line: string) => line.split(';').slice(1).map((p) => p.trim().toLowerCase())

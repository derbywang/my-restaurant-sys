// The kitchen-error channels of a branch: kot_error_<branch>_<production unit>.
// Names are kept as arrays and never joined into one string and split again: branch and production unit names
// contain spaces ("Kitchen - 三友寿司").

type Handler = (payload: Record<string, unknown>) => void;

/** The part of a socket.io socket used here (a fake in the tests). */
export interface SocketLike {
  on(event: string, handler: Handler): unknown;
  off(event: string, handler: Handler): unknown;
}

export function kotErrorChannelNames(branch: string, productions: string[]): string[] {
  if (!branch) return [];
  return productions.filter(Boolean).map((production) => `kot_error_${branch}_${production}`);
}

/** Listen to every channel of the branch; returns the function that stops listening. */
export function subscribeKotErrorChannels(
  socket: SocketLike,
  branch: string,
  productions: string[],
  handler: Handler,
): () => void {
  const names = kotErrorChannelNames(branch, productions);
  names.forEach((name) => socket.on(name, handler));
  return () => names.forEach((name) => socket.off(name, handler));
}

// The colour of the waiting time on a ticket. Red means "the kitchen is slow": a new or modified ticket that waited
// as long as the warning time (POS Profile `custom_kot_warning_time`). A cancel ticket tells the kitchen to stop; its
// time shows how long ago that was said, and stays black, or it would be read as a slow order.

export const TIME_RED = "text-[#DC0000]";
export const TIME_BLACK = "text-black";

const CANCEL_TYPES = ["Cancelled", "Partially cancelled"];

export function timeColor(type, minutes, warningMinutes) {
  const warning = Number(warningMinutes);
  if (CANCEL_TYPES.includes(type)) return TIME_BLACK;
  if (!warning) return TIME_BLACK;
  return minutes >= warning ? TIME_RED : TIME_BLACK;
}

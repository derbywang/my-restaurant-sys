// How long a ticket has been waiting, counted from the date AND the time it was made (so that a ticket of
// yesterday evening is not shown as a negative time after midnight). The card shows "hours : minutes",
// e.g. "1 : 5" is one hour and five minutes.

/** The moment a ticket was made, from its date ("2026-11-06") and time ("18:12:03" or "18:12:03.123456"). */
export function ticketMoment(date, time, now = new Date()) {
  const [hours = 0, minutes = 0, seconds = 0] = String(time || "0:0:0")
    .split(":")
    .map((part) => parseFloat(part) || 0);
  const day = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(date || ""));
  const moment = day
    ? new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]), hours, minutes, Math.floor(seconds))
    : new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes, Math.floor(seconds));
  // a ticket without a date whose time is still to come was made before midnight
  if (!day && moment > now) moment.setDate(moment.getDate() - 1);
  return moment;
}

/** Whole minutes since the ticket was made; never negative (the clocks of two machines differ by a little). */
export function elapsedMinutes(date, time, now = new Date()) {
  return Math.max(0, Math.floor((now - ticketMoment(date, time, now)) / 60000));
}

/** "hours : minutes" as the card shows it. */
export function elapsedLabel(date, time, now = new Date()) {
  const total = elapsedMinutes(date, time, now);
  return `${Math.floor(total / 60)} : ${total % 60}`;
}

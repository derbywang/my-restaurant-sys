/**
 * What happens when a language is picked in the language menu.
 *
 * Every pick is saved, also the language the page shows: another window of the same account may have changed the
 * server's language since this page was loaded, and the server's value is the one that counts.
 *
 * Returns true when the choice was handed to `onSelect` and it succeeded (the app reloads then), false when it
 * failed (`onFailure` is called, the page stays).
 */
export async function chooseLanguage({
  code,
  onSelect,
  onFailure,
}: {
  code: string;
  onSelect: (code: string) => Promise<void>;
  onFailure: (error: unknown) => void;
}): Promise<boolean> {
  try {
    await onSelect(code);
    return true;
  } catch (error) {
    onFailure(error);
    return false;
  }
}

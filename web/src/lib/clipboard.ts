/** Copy text for the learner; false when the browser refuses (the text stays visible to copy by hand). */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** A full link to a hash route of this app, for sending to someone else. */
export function appLink(hash: string): string {
  return `${window.location.origin}${window.location.pathname}${hash}`;
}

export type ActionResult =
  | { ok: true; message?: string; secret?: string }
  | { ok: false; error: string };

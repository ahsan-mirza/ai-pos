const rows = new Map<string, Record<string, unknown>>();

export function rememberRow(moduleId: string, id: string, row: Record<string, unknown>): void {
  rows.set(`${moduleId}:${id}`, row);
}

export function rememberedRow(moduleId: string, id: string): Record<string, unknown> | null {
  return rows.get(`${moduleId}:${id}`) ?? null;
}

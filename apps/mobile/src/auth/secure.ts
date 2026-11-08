import * as SecureStore from "expo-secure-store";

const CHUNK = 1800;

/** Platform secure storage. Values are split because Android rejects large entries. */
export async function secureWrite(key: string, value: string): Promise<void> {
  const count = Math.max(1, Math.ceil(value.length / CHUNK));
  await SecureStore.setItemAsync(`${key}.n`, String(count));
  for (let index = 0; index < count; index += 1) {
    await SecureStore.setItemAsync(`${key}.${index}`, value.slice(index * CHUNK, (index + 1) * CHUNK));
  }
}

export async function secureRead(key: string): Promise<string | null> {
  const countRaw = await SecureStore.getItemAsync(`${key}.n`);
  const count = countRaw === null ? 0 : Number(countRaw);
  if (!Number.isFinite(count) || count <= 0) return null;
  const parts: string[] = [];
  for (let index = 0; index < count; index += 1) {
    const part = await SecureStore.getItemAsync(`${key}.${index}`);
    if (part === null) return null;
    parts.push(part);
  }
  return parts.join("");
}

export async function secureDelete(key: string): Promise<void> {
  const countRaw = await SecureStore.getItemAsync(`${key}.n`);
  const count = countRaw === null ? 0 : Number(countRaw);
  await SecureStore.deleteItemAsync(`${key}.n`);
  for (let index = 0; index < count; index += 1) {
    await SecureStore.deleteItemAsync(`${key}.${index}`);
  }
}

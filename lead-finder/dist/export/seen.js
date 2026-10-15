import { readFile, writeFile } from 'node:fs/promises';
export async function loadSeen(path) {
    try {
        const raw = await readFile(path, 'utf-8');
        const data = JSON.parse(raw);
        return new Set(data.placeIds);
    }
    catch {
        return new Set();
    }
}
export async function saveSeen(path, seen) {
    const data = { placeIds: [...seen] };
    await writeFile(path, JSON.stringify(data, null, 2), 'utf-8');
}

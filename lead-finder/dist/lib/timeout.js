// Timeout propio por llamada al renderer: un evaluate colgado no debe tumbar el run entero.
export function withTimeout(promise, ms, label) {
    return Promise.race([
        promise,
        new Promise((_, reject) => setTimeout(() => reject(new Error(`timeout ${ms}ms en ${label}`)), ms)),
    ]);
}

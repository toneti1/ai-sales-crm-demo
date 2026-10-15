const EMAIL_REGEX = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
const JUNK_LOCAL = /^(noreply|no-reply|donotreply|mailer-daemon|postmaster|example|test|usuario|email|name|your-email)/i;
const JUNK_DOMAIN = /(sentry|wixpress|wordpress|example\.|sentry\.io|@2x|godaddy|domain\.com$)/i;
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|bmp)$/i;
function normalize(raw) {
    let e = raw.toLowerCase().replace(/[\/\\"'`;:>\s]+$/, '').trim();
    const at = e.indexOf('@');
    if (at > 0) {
        const local = e.slice(0, at);
        const m = local.match(/([a-z0-9._%+-]+)$/);
        if (m)
            e = m[1] + e.slice(at);
    }
    return e.replace(/[\/\\"'`;:>\s]+$/, '');
}
export function isJunkEmail(email) {
    const [local, domain] = email.split('@');
    if (!domain)
        return true;
    if (IMAGE_EXT.test(email))
        return true;
    if (JUNK_LOCAL.test(local))
        return true;
    if (JUNK_DOMAIN.test(domain))
        return true;
    return false;
}
export function extractEmails(html) {
    const found = new Set();
    const mailtos = html.matchAll(/mailto:([^"'?>\s]+)/gi);
    for (const m of mailtos) {
        const e = normalize(m[1]);
        if (!isJunkEmail(e))
            found.add(e);
    }
    const plain = html.match(EMAIL_REGEX) ?? [];
    for (const raw of plain) {
        const e = normalize(raw);
        if (!isJunkEmail(e))
            found.add(e);
    }
    // Prioridad: info@ / hola@ / contacto@ primero
    const score = (e) => {
        if (/^(info|hola|contacto|contact|atencion|administracion)@/.test(e))
            return 0;
        return 1;
    };
    return [...found].sort((a, b) => score(a) - score(b));
}

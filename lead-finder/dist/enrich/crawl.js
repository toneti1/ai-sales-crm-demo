import { analyzeSeo } from '../lib/seo.js';
import { extractEmails } from '../lib/email.js';
import { withTimeout } from '../lib/timeout.js';
const PARKED_REGEX = /domain.{0,30}(for sale|se vende)|sedoparking|parkingcrew|hugedomains|buy this domain|este dominio.{0,20}venta|dan\.com|afternic|location\.href.*lander|\/lander["']/i;
const SOCIAL_HOSTS = /^(www\.)?(facebook\.com|instagram\.com|linktr\.ee|wa\.me|api\.whatsapp\.com)/i;
function emptyFacts(siteDown) {
    return {
        siteDown,
        https: false,
        loadTimeMs: 0,
        pageWeightBytes: 0,
        jsErrors: 0,
        hasViewport: false,
        mobileOverflow: false,
        copyrightYear: null,
        isOutdated: false,
        lastContentDate: null,
        cms: null,
        legacyLibs: [],
        formCount: 0,
        hasContactForm: false,
        clickablePhone: false,
        visibleEmail: false,
        whatsapp: false,
        bookingEngine: false,
        ecommerce: false,
        chatWidget: false,
        hasChatbot: false,
        newsletter: false,
        menuPdf: false,
        pricesVisible: false,
        languages: [],
    };
}
async function headExists(url, timeoutMs) {
    try {
        const res = await fetch(url, {
            method: 'GET',
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            signal: AbortSignal.timeout(Math.min(timeoutMs, 6000)),
            redirect: 'follow',
        });
        return res.status !== 404 && res.status < 500;
    }
    catch {
        return false;
    }
}
async function fetchHtml(url, timeoutMs) {
    try {
        const res = await fetch(url, {
            signal: AbortSignal.timeout(Math.min(timeoutMs, 8000)),
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            redirect: 'follow',
        });
        if (!res.ok)
            return { url, html: '' };
        return { url: res.url || url, html: await res.text() };
    }
    catch {
        return { url, html: '' };
    }
}
async function fetchText(url, timeoutMs) {
    return (await fetchHtml(url, timeoutMs)).html;
}
async function fetchTextViaPage(page, url, timeoutMs) {
    return withTimeout(page.evaluate(async (target) => {
        try {
            const res = await fetch(target, { redirect: 'follow' });
            if (!res.ok)
                return '';
            return await res.text();
        }
        catch {
            return '';
        }
    }, url), timeoutMs, 'fetchTextViaPage').catch(() => '');
}
async function fetchRobotsViaPage(page, url, timeoutMs) {
    return withTimeout(page.evaluate(async (target) => {
        try {
            const res = await fetch(target, { redirect: 'follow' });
            if (res.status === 200 || res.status === 403) {
                return await res.text();
            }
            return '';
        }
        catch {
            return '';
        }
    }, url), timeoutMs, 'fetchRobotsViaPage').catch(() => '');
}
async function sitemapExistsViaPage(page, url, timeoutMs) {
    return withTimeout(page.evaluate(async (target) => {
        try {
            const res = await fetch(target, { method: 'HEAD', redirect: 'follow' });
            return res.status !== 404;
        }
        catch {
            return false;
        }
    }, url), timeoutMs, 'sitemapExistsViaPage').catch(() => false);
}
export async function crawlSite(browser, rawUrl, config) {
    const url = rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`;
    const page = await browser.newPage();
    let jsErrors = 0;
    try {
        page.on('pageerror', () => jsErrors++);
        page.on('console', (msg) => {
            if (msg.type() === 'error')
                jsErrors++;
        });
        const started = Date.now();
        let response = null;
        let fetched = null;
        let renderFallback = false;
        try {
            response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: config.timeoutMs });
        }
        catch {
            // Fallback: si Puppeteer da timeout por scripts pesados, probar fetch directo antes de declarar siteDown
            fetched = await fetchHtml(url, config.timeoutMs);
            if (!fetched.html || fetched.html.length < 100) {
                return { status: 'down', finalUrl: null, facts: emptyFacts(true), seoFails: [], emails: [], text: '' };
            }
            renderFallback = true;
        }
        if (!renderFallback && response && !response.ok() && response.status() >= 400 && response.status() !== 403) {
            fetched = await fetchHtml(url, config.timeoutMs);
            if (!fetched.html || fetched.html.length < 100) {
                return { status: 'down', finalUrl: null, facts: emptyFacts(true), seoFails: [], emails: [], text: '' };
            }
            renderFallback = true;
        }
        const finalUrl = renderFallback
            ? (fetched?.url || url)
            : page.url() && page.url() !== 'about:blank'
                ? page.url()
                : url;
        const loadTimeMs = Date.now() - started;
        const finalHost = new URL(finalUrl).hostname;
        if (SOCIAL_HOSTS.test(finalHost)) {
            return { status: 'social', finalUrl, facts: null, seoFails: [], emails: [], text: '' };
        }
        let html = renderFallback
            ? (fetched?.html ?? '')
            : await withTimeout(page.content(), 15000, 'page.content').catch(() => '');
        if (!renderFallback && (!html || html.length < 20000)) {
            const full = await fetchHtml(finalUrl, 10000);
            if (full.html.length > html.length) {
                html = full.html;
            }
        }
        if (PARKED_REGEX.test(html)) {
            return { status: 'parked', finalUrl, facts: null, seoFails: [], emails: [], text: '' };
        }
        // Breve espera para que los maquetadores dinámicos desplieguen su texto
        await page.evaluate(() => new Promise((r) => setTimeout(r, 1000))).catch(async () => {
            await new Promise((r) => setTimeout(r, 1500));
        });
        const evaluateDom = (textMaxChars) => {
            const text = document.body?.innerText ?? '';
            const wordCount = text.split(/\s+/).filter(Boolean).length;
            const weight = performance
                .getEntriesByType('resource')
                .reduce((acc, e) => acc + (e.transferSize || 0), 0);
            const viewportMeta = !!document.querySelector('meta[name="viewport"]');
            const docLang = document.documentElement.lang || null;
            const hreflangs = [...document.querySelectorAll('link[hreflang]')].map((l) => l.getAttribute('hreflang') ?? '');
            const languages = [...new Set([docLang, ...hreflangs].filter(Boolean))];
            const jquery = window.jQuery?.fn?.jquery ?? null;
            const generator = document
                .querySelector('meta[name="generator"]')
                ?.getAttribute('content') ?? null;
            const forms = document.querySelectorAll('form');
            const formIframes = document.querySelectorAll('iframe[src*="form/" i], iframe[src*="form." i], iframe[src*="forms." i], iframe[src*="-form" i], iframe[src*="_form" i], iframe[src*="form-" i], iframe[src*="form_" i], iframe[src*="lead" i], iframe[src*="hubspot" i], iframe[src*="calendly" i], iframe[src*="typeform" i], iframe[src*="tally" i], iframe[src*="gohighlevel" i], iframe[src*="leadconnector" i]');
            const totalForms = forms.length + formIframes.length;
            const hasFormInput = !!document.querySelector('form input[type="email"], form textarea, form input[type="tel"], .elementor-form, [class*="elementor-form" i]') ||
                formIframes.length > 0;
            return {
                text: text.slice(0, textMaxChars),
                wordCount,
                pageWeightBytes: weight,
                viewportMeta,
                languages,
                jqueryVersion: jquery,
                generator,
                formCount: totalForms,
                hasContactForm: hasFormInput,
                clickablePhone: !!document.querySelector('a[href^="tel:"]'),
                mailtoPresent: !!document.querySelector('a[href^="mailto:"]'),
                whatsapp: Array.from(document.querySelectorAll('a[href]')).some((a) => /wa\.me|whatsapp\.com|whatsapp:|send\?phone/i.test(a.getAttribute('href') || '')) ||
                    !!document.querySelector('[class*="whatsapp" i], [id*="whatsapp" i], [class*="joinchat" i], [id*="joinchat" i], [class*="wsp" i], [aria-label*="whatsapp" i]'),
                htmlLang: docLang,
            };
        };
        let rendered = null;
        try {
            rendered = await withTimeout(page.evaluate(evaluateDom, config.textMaxChars), 20000, 'crawl.rendered');
        }
        catch (err) {
            if (err?.message?.includes('Execution context was destroyed') || err?.message?.includes('navigation')) {
                await new Promise((r) => setTimeout(r, 1500));
                rendered = await withTimeout(page.evaluate(evaluateDom, config.textMaxChars), 20000, 'crawl.rendered').catch(() => null);
            }
        }
        if (!rendered) {
            const fallbackText = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
            rendered = {
                text: fallbackText.slice(0, config.textMaxChars),
                wordCount: fallbackText.split(/\s+/).filter(Boolean).length,
                pageWeightBytes: html.length,
                viewportMeta: /<meta[^>]+viewport/i.test(html),
                languages: [],
                jqueryVersion: null,
                generator: null,
                formCount: (html.match(/<form[\s>]/gi) || []).length,
                hasContactForm: /<form[\s>]/i.test(html),
                clickablePhone: /href=["']tel:/i.test(html),
                mailtoPresent: /href=["']mailto:/i.test(html),
                whatsapp: /wa\.me|whatsapp\.com|joinchat/i.test(html),
                htmlLang: null,
            };
        }
        // Fallback de formularios en HTML raw (para popups/templates de Elementor no adjuntados al DOM inmediatamente)
        const rawFormMatchCount = (html.match(/<form[\s>]/gi) || []).length;
        const finalFormCount = Math.max(rendered.formCount, rawFormMatchCount);
        const finalHasContactForm = rendered.hasContactForm || rawFormMatchCount > 0 || /<form[\s>]/i.test(html) || /class=["'][^"']*elementor-form/i.test(html);
        // Overflow movil: segundo render a 375px
        let mobileOverflow = false;
        if (!renderFallback) {
            await withTimeout(page.setViewport({ width: 375, height: 812 }), 10000, 'crawl.viewport').catch(() => { });
            mobileOverflow = await withTimeout(page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 5), 10000, 'crawl.mobileOverflow').catch(() => false);
        }
        // Facts derived from HTML (server-side regex, no more renders)
        const lowerHtml = html.toLowerCase();
        const currentYear = new Date().getFullYear();
        const copyrightMatch = html.match(/(?:©|&copy;|copyright)[^0-9]{0,20}((?:19|20)\d{2})/i);
        const copyrightYear = copyrightMatch ? parseInt(copyrightMatch[1], 10) : null;
        const dateMatches = [...html.matchAll(/\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b/g)]
            .map((m) => new Date(`${m[3]}-${m[2]}-${m[1]}`))
            .filter((d) => !isNaN(d.getTime()) && d.getTime() < Date.now())
            .sort((a, b) => b.getTime() - a.getTime());
        const lastContentDate = dateMatches[0]?.toISOString().slice(0, 10) ?? null;
        const staleContent = dateMatches.length > 0 &&
            Date.now() - dateMatches[0].getTime() > 365 * 24 * 3600 * 1000;
        const CMS_ALIASES = {
            wordpress: 'WordPress',
            joomla: 'Joomla',
            drupal: 'Drupal',
            magento: 'Magento',
            prestashop: 'PrestaShop',
            shopify: 'Shopify',
            wix: 'Wix',
            squarespace: 'Squarespace',
            webflow: 'Webflow',
            weebly: 'Weebly',
            jimdo: 'Jimdo',
            webnode: 'Webnode',
            godaddy: 'GoDaddy',
            typo3: 'TYPO3',
            ghost: 'Ghost',
            blogger: 'Blogger',
            modx: 'MODX',
            umbraco: 'Umbraco',
            django: 'Django CMS',
            nextjs: 'Next.js',
            'next.js': 'Next.js',
            nuxtjs: 'Nuxt.js',
            'nuxt.js': 'Nuxt.js',
            gatsby: 'Gatsby',
            astro: 'Astro',
            sveltekit: 'SvelteKit',
            remix: 'Remix',
            laravel: 'Laravel',
        };
        function cmsFromGenerator(raw) {
            if (!raw)
                return null;
            const lower = raw.toLowerCase();
            for (const [key, name] of Object.entries(CMS_ALIASES)) {
                if (lower.includes(key))
                    return name;
            }
            // Ignorar generadores de plugins/versiones largas
            if (/\b(v?\d+\.\d+|version| by |plugin|addon|module|wpml|site kit|yoast|elementor)\b/i.test(raw)) {
                return null;
            }
            if (raw.length > 40)
                return null;
            return raw;
        }
        let cms = null;
        const rawGen = rendered.generator ?? '';
        if (lowerHtml.includes('wp-content') || lowerHtml.includes('wp-includes') || /wordpress/i.test(rawGen)) {
            cms = 'WordPress';
        }
        else if (lowerHtml.includes('astro-build') || lowerHtml.includes('_astro') || lowerHtml.includes('astro') || /astro/i.test(rawGen)) {
            cms = 'Astro';
        }
        else if (lowerHtml.includes('next.js') || lowerHtml.includes('__next') || /next/i.test(rawGen)) {
            cms = 'Next.js';
        }
        else if (lowerHtml.includes('nuxt') || lowerHtml.includes('__nuxt') || /nuxt/i.test(rawGen)) {
            cms = 'Nuxt.js';
        }
        else if (lowerHtml.includes('gatsby') || /gatsby/i.test(rawGen)) {
            cms = 'Gatsby';
        }
        else if (lowerHtml.includes('webflow') || /webflow/i.test(rawGen)) {
            cms = 'Webflow';
        }
        else if (lowerHtml.includes('wix.com') || lowerHtml.includes('x-wix') || /wix/i.test(rawGen)) {
            cms = 'Wix';
        }
        else if (lowerHtml.includes('shopify') || /shopify/i.test(rawGen)) {
            cms = 'Shopify';
        }
        else if (lowerHtml.includes('joomla') || /joomla/i.test(rawGen)) {
            cms = 'Joomla';
        }
        else if (lowerHtml.includes('webnode') || /webnode/i.test(rawGen)) {
            cms = 'Webnode';
        }
        else if (lowerHtml.includes('jimdo') || /jimdo/i.test(rawGen)) {
            cms = 'Jimdo';
        }
        else if (lowerHtml.includes('squarespace') || /squarespace/i.test(rawGen)) {
            cms = 'Squarespace';
        }
        else {
            const fromGen = cmsFromGenerator(rawGen);
            if (fromGen)
                cms = fromGen;
        }
        const legacyLibs = [];
        if (rendered.jqueryVersion && parseInt(rendered.jqueryVersion, 10) < 3) {
            legacyLibs.push(`jQuery ${rendered.jqueryVersion}`);
        }
        const bootstrapMatch = lowerHtml.match(/bootstrap(?:\.min)?\.css[^"]*\?ver=([0-9.]+)|bootstrap@([0-9.]+)/);
        if (bootstrapMatch && parseInt(bootstrapMatch[1] ?? bootstrapMatch[2] ?? '5', 10) < 4) {
            legacyLibs.push('Bootstrap <4');
        }
        const bookingEngine = /calendly|booksy|simplybook|covermanager|eltenedor|thefork|doctolib|reservio|fresha|treatwell|planfy|simplybookit|vagaro|squareup|setmore|appointy|10to8|trafft|zyllion|timetap|https?:\/\/(www\.)?(calendly|booksy|simplybook|doctolib|reservio|fresha|treatwell|planfy|vagaro|setmore|appointy|10to8|trafft|zyllion|timetap)\./i.test(html);
        const ecommerce = /add[- ]?to[- ]?cart|añadir al carrito|woocommerce|shopify|cart-item|checkout/i.test(html);
        const chatWidget = /intercom|tidio|crisp\.chat|drift\.com|livechatinc|tawk\.to|hubspot.*conversations|zendesk.*chat/i.test(lowerHtml);
        const hasChatbot = chatWidget && /chatbot|asistente virtual|ai assistant|botpress|voiceflow/i.test(lowerHtml);
        const newsletter = /newsletter|suscr[ií]bete|subscribe/i.test(html) && rendered.hasContactForm;
        const menuPdf = /<a[^>]+href=["'][^"']*\.pdf["'][^>]*>[^<]*(carta|men[uú])|href=["'][^"']*(carta|menu)[^"']*\.pdf/i.test(html);
        const priceMatches = html.match(/\d+[.,]?\d{0,2}\s*€|\€\s*\d+/g) ?? [];
        const pricesVisible = priceMatches.length > 3;
        const urlObj = new URL(finalUrl);
        const origin = urlObj.origin;
        const hostParts = urlObj.hostname.split('.');
        const rootHost = hostParts.length >= 2 ? hostParts.slice(-2).join('.') : urlObj.hostname;
        const rootOrigin = `${urlObj.protocol}//${rootHost}`;
        const [robotsOrigin, robotsRoot] = await Promise.all([
            fetchText(`${origin}/robots.txt`, config.timeoutMs),
            rootOrigin !== origin ? fetchText(`${rootOrigin}/robots.txt`, config.timeoutMs) : Promise.resolve(''),
        ]);
        let robotsTxtContent = robotsOrigin || robotsRoot;
        if (!robotsTxtContent) {
            // Si Node fetch falla (TLS/WAF), pedir al navegador primero el origin real y luego el root
            robotsTxtContent = await fetchRobotsViaPage(page, `${origin}/robots.txt`, config.timeoutMs);
            if (!robotsTxtContent && rootOrigin !== origin) {
                robotsTxtContent = await fetchRobotsViaPage(page, `${rootOrigin}/robots.txt`, config.timeoutMs);
            }
        }
        const hasRobotsTxt = robotsTxtContent.length > 0 ||
            /User-agent/i.test(robotsTxtContent) ||
            (await headExists(`${origin}/robots.txt`, config.timeoutMs)) ||
            (rootOrigin !== origin && (await headExists(`${rootOrigin}/robots.txt`, config.timeoutMs)));
        const declaredSitemapInRobots = /sitemap:\s*http/i.test(robotsTxtContent);
        let sitemapExists = (await headExists(`${origin}/sitemap.xml`, config.timeoutMs)) ||
            (await headExists(`${origin}/sitemap_index.xml`, config.timeoutMs)) ||
            (rootOrigin !== origin &&
                ((await headExists(`${rootOrigin}/sitemap.xml`, config.timeoutMs)) ||
                    (await headExists(`${rootOrigin}/sitemap_index.xml`, config.timeoutMs))));
        if (!sitemapExists && !declaredSitemapInRobots) {
            const sitemapBases = rootOrigin !== origin ? [origin, rootOrigin] : [origin];
            outer: for (const base of sitemapBases) {
                for (const sitemapPath of ['/sitemap.xml', '/sitemap_index.xml']) {
                    if (await sitemapExistsViaPage(page, `${base}${sitemapPath}`, config.timeoutMs)) {
                        sitemapExists = true;
                        break outer;
                    }
                }
            }
        }
        const hasSitemapXml = declaredSitemapInRobots || sitemapExists;
        const seoFails = analyzeSeo({
            html,
            textWordCount: rendered.wordCount,
            hasRobotsTxt,
            hasSitemapXml,
            isHttps: finalUrl.startsWith('https://'),
            thinContentWords: config.thinContentWords,
            imgNoAltRatio: config.imgNoAltRatio,
        });
        // Emails: homepage + paginas de contacto via fetch directo; fallback por el navegador si WAF bloquea Node fetch
        const emailSet = new Set(extractEmails(html));
        if (emailSet.size === 0) {
            for (const path of config.emailPaths) {
                const pageUrl = `${origin}${path}`;
                let pageHtml = await fetchText(pageUrl, config.timeoutMs);
                if (!pageHtml && !renderFallback) {
                    pageHtml = await fetchTextViaPage(page, pageUrl, config.timeoutMs);
                }
                if (pageHtml) {
                    for (const e of extractEmails(pageHtml))
                        emailSet.add(e);
                    if (emailSet.size > 0)
                        break;
                }
            }
        }
        const hasRecentContent = dateMatches.length > 0 && Date.now() - dateMatches[0].getTime() < 365 * 24 * 3600 * 1000;
        const isOutdated = staleContent || (copyrightYear !== null && copyrightYear < currentYear - 4 && !hasRecentContent);
        const facts = {
            siteDown: false,
            https: finalUrl.startsWith('https://'),
            loadTimeMs,
            pageWeightBytes: rendered.pageWeightBytes,
            jsErrors,
            hasViewport: rendered.viewportMeta,
            mobileOverflow,
            copyrightYear,
            isOutdated,
            lastContentDate,
            cms,
            legacyLibs,
            formCount: finalFormCount,
            hasContactForm: finalHasContactForm,
            clickablePhone: rendered.clickablePhone,
            visibleEmail: rendered.mailtoPresent || emailSet.size > 0,
            whatsapp: rendered.whatsapp || /wa\.me|whatsapp\.com|whatsapp:|api\.whatsapp\.com|joinchat|wsp-float/i.test(lowerHtml),
            bookingEngine,
            ecommerce,
            chatWidget,
            hasChatbot,
            newsletter,
            menuPdf,
            pricesVisible,
            languages: rendered.languages,
        };
        return {
            status: 'ok',
            finalUrl,
            facts,
            seoFails,
            emails: [...emailSet],
            text: rendered.text,
        };
    }
    finally {
        await page.close();
    }
}

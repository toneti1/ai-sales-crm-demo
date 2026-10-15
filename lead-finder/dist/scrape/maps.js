import puppeteer from 'puppeteer';
import { addExtra } from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { withTimeout } from '../lib/timeout.js';
// ponytail: puppeteer-extra 3.x tipa contra API antigua de puppeteer (createBrowserFetcher).
// Runtime funciona con puppeteer 23; el cast solo silencia el tipo. Upgrade: puppeteer-extra v4 cuando sea estable.
const puppeteerExtra = addExtra(puppeteer);
puppeteerExtra.use(StealthPlugin());
const DIRECTORY_AND_SOCIAL_HOSTS = [
    // Redes Sociales y Mensajería
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linktr.ee', 'linktree', 'wa.me', 'whatsapp.com', 'linkedin.com', 'youtube.com', 'tiktok.com',
    // España (Nacional)
    'doctoralia.', 'topdoctors.', 'habitissimo.', 'cronoshare.', 'paginasamarillas.',
    // Reino Unido / Irlanda
    'yell.com', 'thomsonlocal.com', '192.com', 'scoot.co.uk', 'freeindex.co.uk', 'bark.com', 'checkatrade.com', 'trustatrader.com', 'mybuilder.com', 'goldenpages.ie',
    // Alemania
    'gelbeseiten.de', '11880.com', 'dasoertliche.de', 'golocal.de', 'goyellow.de', 'jameda.de',
    // Francia
    'pagesjaunes.fr', 'pagespro.com', 'doctolib.', 'malt.',
    // Italia
    'paginegialle.it', 'miodottore.it',
    // Países Bajos / Bélgica
    'zorgkaartnederland.nl', 'goudengids.nl', 'pagesdor.be', 'goudengids.be',
    // Suiza / Austria / Portugal
    'local.ch', 'search.ch', 'herold.at', 'paginasamarelas.pt',
    // Polonia / Chequia / Eslovaquia
    'znanylekarz.pl', 'panoramafirm.pl', 'zlatestranky.', 'znamylekar.cz',
    // Escandinavia / Finlandia
    'eniro.se', 'gulasidorna.se', 'hitta.se', 'gulesider.no', 'proff.no', 'kvasir.no', 'krak.dk', 'degulesider.dk', 'keltaisetsivut.fi',
    // Turquía y Globales
    'doktortakvimi.com', 'yelp.com', 'tripadvisor.', 'trustpilot.com',
];
const SOCIAL_HOSTS_REGEX = new RegExp(DIRECTORY_AND_SOCIAL_HOSTS.map((h) => h.replace(/\./g, '\\.')).join('|'), 'i');
function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}
function rand(range) {
    return Math.floor(range[0] + Math.random() * (range[1] - range[0]));
}
export function isSocialUrl(url) {
    return SOCIAL_HOSTS_REGEX.test(url);
}
async function handleConsent(page) {
    if (!/consent/.test(page.url()))
        return;
    const clickStr = `(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
      const t = (b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '');
      return /rechazar todo|reject all|aceptar todo|accept all/i.test(t);
    });
    if (btn) { btn.click(); return true; }
    return false;
  })()`;
    for (let attempt = 0; attempt < 3; attempt++) {
        await sleep(2500);
        try {
            const clicked = await withTimeout(page.evaluate(clickStr), 10000, 'handleConsent.click');
            if (!clicked)
                continue;
            await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => { });
            await sleep(2000);
            if (!/consent/.test(page.url()))
                return;
        }
        catch {
            // evaluate colgado: reintentar
        }
    }
}
async function scrollFeed(page, feedSelector, pause) {
    try {
        const script = `((sel) => {
      const feed = document.querySelector(sel);
      if (!feed) return false;
      const before = feed.scrollTop;
      feed.scrollBy(0, feed.scrollHeight);
      return feed.scrollTop !== before || feed.scrollHeight > feed.clientHeight;
    })('${feedSelector}')`;
        const grew = await withTimeout(page.evaluate(script), 15000, 'scrollFeed');
        await sleep(rand(pause));
        return Boolean(grew);
    }
    catch {
        await sleep(rand(pause));
        return false;
    }
}
async function visibleFeedItems(page) {
    try {
        const script = `(() => {
      const anchors = Array.from(document.querySelectorAll('a[href*="/maps/place/"]'));
      const items = [];
      for (const a of anchors) {
        const m = a.href.match(/!1s([^!]+)/);
        const placeId = m ? m[1] : a.href;
        const name = a.getAttribute('aria-label') || a.textContent || '';
        const cleanName = name.trim();
        if (cleanName) items.push({ placeId: placeId, name: cleanName, href: a.href });
      }
      return items;
    })()`;
        return await withTimeout(page.evaluate(script), 15000, 'visibleFeedItems');
    }
    catch {
        return [];
    }
}
function countUsableItems(items, excluded) {
    let count = 0;
    for (const placeId of items.keys()) {
        if (!excluded?.has(placeId))
            count++;
    }
    return count;
}
async function extractDetailFromUrl(browser, url) {
    const page = await browser.newPage();
    try {
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await handleConsent(page);
        await page
            .waitForSelector('button[data-item-id^="phone"], a[data-item-id="authority"], button[data-item-id^="address"], div[role="main"]', {
            timeout: 10000,
        })
            .catch(() => { });
        await sleep(1000);
        return await extractDetail(page);
    }
    finally {
        await page.close().catch(() => { });
    }
}
async function extractDetail(page) {
    const script = `(() => {
    const byItemId = (prefix, tag) => document.querySelector((tag || 'button') + '[data-item-id^="' + prefix + '"]');

    const websiteA = document.querySelector('a[data-item-id="authority"]');
    const phoneBtn = byItemId('phone');
    const addressBtn = byItemId('address');

    const clean = (label) => {
      if (!label) return null;
      const idx = label.indexOf(':');
      return (idx >= 0 ? label.slice(idx + 1) : label).trim() || null;
    };

    let rating = null;
    let reviewCount = 0;

    const mainContainer = document.querySelector('div[role="main"]') || document.body;

    const ratingEl = mainContainer.querySelector('[role="img"][aria-label*="estrella"], [role="img"][aria-label*="star"], span[aria-label*="estrella"]');
    if (ratingEl) {
      const label = ratingEl.getAttribute('aria-label') || '';
      const m = label.match(/(\\d+[.,]\\d+)/);
      if (m) rating = parseFloat(m[1].replace(',', '.'));
    }

    const headerBtns = Array.from(mainContainer.querySelectorAll('button[aria-label*="reseña"], button[aria-label*="review"], button[aria-label*="opinión"], span[aria-label*="reseña"], span[aria-label*="review"]'));
    for (const btn of headerBtns) {
      const txt = btn.getAttribute('aria-label') || btn.textContent || '';
      const m = txt.match(/\\((\\d[\\d\\s.,]*)\\)/) || txt.match(/(\\d[\\d\\s.,]*)\\s*(?:reseña|review|opinión)/i);
      if (m) {
        const val = parseInt(m[1].replace(/[^\\d]/g, ''), 10);
        if (!isNaN(val) && val > 0 && val < 1000000) {
          reviewCount = val;
          break;
        }
      }
    }

    if (reviewCount === 0) {
      // Fallback por spans de texto en el panel lateral
      const spans = mainContainer.querySelectorAll('span, button, div[role="button"]');
      for (const el of spans) {
        const txt = (el.getAttribute('aria-label') || el.textContent || '').trim();
        const m = txt.match(/\\((\\d[\\d\\s.,]*)\\)/) || txt.match(/(\\d[\\d\\s.,]*)\\s*(?:reseñas?|reviews?|opiniones|valoraciones)/i);
        if (m) {
          const val = parseInt(m[1].replace(/[^\\d]/g, ''), 10);
          if (!isNaN(val) && val > 0 && val < 1000000) {
            reviewCount = val;
            break;
          }
        }
      }
    }

    if (reviewCount === 0) {
      const lines = mainContainer.innerText.split('\\n').map((l) => l.trim()).filter(Boolean);
      for (let i = 0; i < Math.min(lines.length, 20); i++) {
        const line = lines[i];
        if (/^\\d+[.,]\\d+$/.test(line) && !rating) {
          rating = parseFloat(line.replace(',', '.'));
        }
        const pm = line.match(/^\\((\\d[\\d\\s.,]*)\\)$/) || line.match(/^(\\d[\\d\\s.,]*)\\s*(?:reseñas?|reviews?|opiniones|valoraciones)$/i);
        if (pm) {
          const val = parseInt(pm[1].replace(/[^\\d]/g, ''), 10);
          if (!isNaN(val) && val > 0) {
            reviewCount = val;
            break;
          }
        }
      }
    }

    function findPhone(text) {
      // Prioridad: formato internacional con +
      const intlMatches = text.match(/\\+\\d{1,3}(?:[\\s().-]?\\(?\\d{1,4}\\)?){1,4}/g) || [];
      const intl = intlMatches
        .map((m) => m.replace(/[^\\d+]/g, ''))
        .filter((m) => m.length >= 8 && m.length <= 15)
        .sort((a, b) => b.length - a.length)[0];
      if (intl) return intl;
      // Fallback para móviles/fijos españoles sin prefijo
      const es = text.match(/[6789]\\d{2}[\\s.-]?\\d{2}[\\s.-]?\\d{2}[\\s.-]?\\d{2}/);
      if (es) return es[0].trim();
      return null;
    }

    let phoneVal = clean(phoneBtn ? phoneBtn.getAttribute('aria-label') || phoneBtn.textContent : null);
    if (!phoneVal) {
      const telA = document.querySelector('a[href^="tel:"]');
      if (telA) {
        phoneVal = clean(telA.getAttribute('href') || telA.textContent);
      } else {
        phoneVal = findPhone(mainContainer ? mainContainer.innerText : '');
      }
    }

    const categoryBtn = document.querySelector('button[jsaction*="category"]');

    return {
      website: websiteA ? websiteA.href : null,
      phone: phoneVal,
      address: clean(addressBtn ? addressBtn.getAttribute('aria-label') || addressBtn.textContent : null),
      rating: rating,
      reviewCount: reviewCount,
      category: categoryBtn ? categoryBtn.textContent.trim() : null,
    };
  })()`;
    return withTimeout(page.evaluate(script), 20000, 'extractDetail');
}
export async function launchBrowser() {
    return puppeteerExtra.launch({
        headless: true,
        protocolTimeout: 120000,
        args: ['--lang=es-ES', '--no-sandbox', '--disable-blink-features=AutomationControlled'],
        defaultViewport: { width: 1366, height: 900 },
    });
}
export async function scrapeMaps(browser, city, sector, config, onProgress, options = {}) {
    const page = await browser.newPage();
    const results = [];
    const seen = new Set();
    const excluded = options.excludePlaceIds;
    try {
        const query = `${sector} en ${city}`;
        await page.goto(`https://www.google.com/maps/search/${encodeURIComponent(query)}?hl=es`, {
            waitUntil: 'domcontentloaded',
            timeout: 30000,
        });
        await handleConsent(page);
        onProgress?.(`[debug] URL tras consent: ${page.url().slice(0, 80)}`);
        if (/consent/.test(page.url())) {
            await page.goto(`https://www.google.com/maps/search/${encodeURIComponent(query)}?hl=es`, {
                waitUntil: 'domcontentloaded',
                timeout: 30000,
            }).catch(() => { });
            await handleConsent(page);
            onProgress?.(`[debug] URL tras re-goto: ${page.url().slice(0, 80)}`);
        }
        const found = await page
            .waitForSelector('a[href*="/maps/place/"]', { timeout: 30000 })
            .then(() => true)
            .catch(() => false);
        onProgress?.(`[debug] anchors de resultados: ${found ? 'OK' : 'NO aparecieron'}`);
        await sleep(rand(config.scrollPauseMs));
        // PHASE 1: collect feed items using scroll only
        const items = new Map();
        let staleRounds = 0;
        let guard = 0;
        const MAX_GUARD = 200;
        const MAX_STALE = 6;
        while (countUsableItems(items, excluded) < config.maxResults && guard++ < MAX_GUARD) {
            try {
                const foundItems = await visibleFeedItems(page);
                for (const it of foundItems)
                    items.set(it.placeId, it);
                if (countUsableItems(items, excluded) >= config.maxResults)
                    break;
                await scrollFeed(page, 'div[role="feed"]', config.scrollPauseMs);
                const after = await visibleFeedItems(page);
                let grew = false;
                for (const it of after) {
                    if (!items.has(it.placeId)) {
                        items.set(it.placeId, it);
                        grew = true;
                    }
                }
                staleRounds = grew ? 0 : staleRounds + 1;
                if (staleRounds >= MAX_STALE)
                    break;
            }
            catch (loopErr) {
                onProgress?.(`[warn] scroll loop retry: ${loopErr instanceof Error ? loopErr.message : String(loopErr)}`);
                await sleep(2000);
            }
        }
        const usableCount = countUsableItems(items, excluded);
        const skippedSeenCount = items.size - usableCount;
        onProgress?.(`[debug] ${usableCount} candidate businesses (${items.size} listed, ${skippedSeenCount} already seen)`);
        // PHASE 2: details by URL in a new page
        const targets = [...items.values()]
            .filter((item) => !excluded?.has(item.placeId))
            .slice(0, config.maxResults);
        let consecutiveErrors = 0;
        const MAX_CONSECUTIVE_ERRORS = 3;
        for (const target of targets) {
            if (seen.has(target.placeId))
                continue;
            seen.add(target.placeId);
            try {
                const detail = await extractDetailFromUrl(browser, target.href);
                results.push({
                    placeId: target.placeId,
                    name: target.name,
                    mapsUrl: target.href,
                    ...detail,
                });
                consecutiveErrors = 0;
                onProgress?.(`[${results.length}] ${target.name}`);
            }
            catch (err) {
                consecutiveErrors++;
                onProgress?.(`[warn] detail failed for ${target.name} (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS}): ${err instanceof Error ? err.message : String(err)}`);
                if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                    onProgress?.('[stop] too many consecutive failures, stopping with partial results');
                    break;
                }
            }
            await sleep(rand(config.detailDelayMs));
        }
        if (guard >= MAX_GUARD) {
            onProgress?.('[stop] iteration limit reached, stopping for safety');
        }
    }
    catch (err) {
        onProgress?.(`[warn] scrapeMaps aborted: ${err instanceof Error ? err.message : String(err)}`);
    }
    finally {
        await page.close().catch(() => { });
    }
    return results;
}

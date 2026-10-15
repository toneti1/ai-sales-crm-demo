import { readFile, writeFile, copyFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { z } from 'zod';
import { launchBrowser, scrapeMaps, isSocialUrl } from './scrape/maps.js';
import { crawlSite } from './enrich/crawl.js';
import { buildRuleBasedAudit } from './audit/ruleBased.js';
import { buildTemplateAudit } from './audit/template.js';
import { sizeFromReviews } from './lib/size.js';
import { computePriority } from './lib/priority.js';
import { isRelevantCategory } from './lib/categoryFilter.js';
import { loadSeen, saveSeen } from './export/seen.js';
import { LeadsFileSchema } from './types.js';
const ConfigSchema = z.object({
    maps: z.object({
        maxResults: z.number(),
        scrollPauseMs: z.tuple([z.number(), z.number()]),
        detailDelayMs: z.tuple([z.number(), z.number()]),
        locale: z.string(),
    }),
    crawl: z.object({
        timeoutMs: z.number(),
        slowLoadMs: z.number(),
        heavyPageBytes: z.number(),
        textMaxChars: z.number(),
        emailPaths: z.array(z.string()),
        thinContentWords: z.number(),
        imgNoAltRatio: z.number(),
    }),
    audit: z.object({
        maxAuditsPerRun: z.number(),
        model: z.string(),
        requestDelayMs: z.number(),
    }),
});
function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}
function classifySegment(website) {
    if (!website)
        return { segment: 'A', cleanWebsite: null };
    if (isSocialUrl(website))
        return { segment: 'A', cleanWebsite: website };
    return { segment: 'B', cleanWebsite: website };
}
export async function run(options) {
    loadEnv();
    const configPath = options.configPath ?? 'config.json';
    const configRaw = JSON.parse(await readFile(configPath, 'utf-8'));
    const config = ConfigSchema.parse(configRaw);
    const mapsConfig = {
        ...config.maps,
        maxResults: options.maxResults ?? config.maps.maxResults,
    };
    const crawlConfig = config.crawl;
    const maxAudits = options.maxAudits ?? config.audit.maxAuditsPerRun;
    const seenPath = options.seenPath ?? 'seen.json';
    const outPath = options.outPath ?? 'leads.json';
    console.log(`Searching for "${options.sector}" in "${options.city}" (max ${mapsConfig.maxResults})...`);
    const browser = await launchBrowser();
    let leads = [];
    try {
        const seen = await loadSeen(seenPath);
        const raw = await scrapeMaps(browser, options.city, options.sector, mapsConfig, (msg) => console.log(`  ${msg}`), { excludePlaceIds: options.includeSeen ? undefined : seen });
        console.log(`${raw.length} businesses found. Enriching...`);
        let auditsUsed = 0;
        let skippedSeen = 0;
        for (const business of raw) {
            if (!options.includeSeen && seen.has(business.placeId)) {
                skippedSeen++;
                continue;
            }
            if (!isRelevantCategory(business.category, options.sector)) {
                console.log(`  [skip] Irrelevant category skipped: "${business.name}" (${business.category})`);
                continue;
            }
            const { segment, cleanWebsite } = classifySegment(business.website);
            let lead = {
                placeId: business.placeId,
                name: business.name,
                phone: business.phone,
                address: business.address,
                website: cleanWebsite,
                mapsUrl: business.mapsUrl,
                rating: business.rating,
                reviewCount: business.reviewCount,
                category: business.category,
                city: options.city,
                sector: options.sector,
                segment,
                size: sizeFromReviews(business.reviewCount),
                email: null,
                facts: null,
                seoFails: [],
                audit: null,
                auditStatus: 'pending',
                priority: 'low',
                reasons: [],
            };
            if (segment === 'A') {
                lead.audit = buildTemplateAudit({
                    name: lead.name,
                    sector: lead.sector,
                    city: lead.city,
                    siteDown: false,
                    socialOnly: business.website !== null,
                });
                lead.auditStatus = 'template';
                lead.seoFails = lead.audit.seoFails;
            }
            else if (cleanWebsite) {
                console.log(`  Crawl: ${lead.name} -> ${cleanWebsite}`);
                let crawl;
                try {
                    crawl = await crawlSite(browser, cleanWebsite, crawlConfig);
                }
                catch (err) {
                    // Crawl failed hard (hung renderer, etc.): treat as a down site and continue
                    console.warn(`  [warn] crawl failed for ${lead.name}: ${err instanceof Error ? err.message : String(err)}`);
                    crawl = { status: 'down', finalUrl: null, facts: null, seoFails: [], emails: [], text: '' };
                }
                if (crawl.status === 'parked' || crawl.status === 'social') {
                    // Parked domain or social redirect: reclassify as segment A
                    lead.segment = 'A';
                    lead.website = null;
                    lead.audit = buildTemplateAudit({
                        name: lead.name,
                        sector: lead.sector,
                        city: lead.city,
                        siteDown: false,
                        socialOnly: crawl.status === 'social',
                    });
                    lead.auditStatus = 'template';
                    lead.seoFails = lead.audit.seoFails;
                }
                else if (crawl.status === 'down') {
                    lead.audit = buildTemplateAudit({
                        name: lead.name,
                        sector: lead.sector,
                        city: lead.city,
                        siteDown: true,
                        socialOnly: false,
                    });
                    lead.auditStatus = 'template';
                    lead.seoFails = lead.audit.seoFails;
                }
                else {
                    lead.facts = crawl.facts;
                    lead.seoFails = crawl.seoFails;
                    lead.email = crawl.emails[0] ?? null;
                    // Update website to the real final URL after redirects (e.g. http -> https)
                    if (crawl.finalUrl && crawl.finalUrl !== lead.website) {
                        lead.website = crawl.finalUrl;
                        const reclassified = classifySegment(lead.website);
                        lead.segment = reclassified.segment;
                    }
                    if (crawl.facts) {
                        lead.audit = buildRuleBasedAudit({
                            name: lead.name,
                            sector: lead.sector,
                            city: lead.city,
                            rating: lead.rating,
                            reviewCount: lead.reviewCount,
                            facts: crawl.facts,
                            seoFails: crawl.seoFails,
                            text: crawl.text,
                        });
                        lead.auditStatus = 'done';
                    }
                }
            }
            const { priority, reasons } = computePriority({
                email: lead.email,
                segment: lead.segment,
                seoFailsCount: lead.seoFails.length,
                rating: lead.rating,
                reviewCount: lead.reviewCount,
                phone: lead.phone,
            });
            lead.priority = priority;
            lead.reasons = reasons;
            leads.push(lead);
            seen.add(business.placeId);
        }
        if (skippedSeen > 0) {
            console.log(`  ${skippedSeen} already-seen businesses skipped during enrichment.`);
        }
        await saveSeen(seenPath, seen);
    }
    finally {
        await browser.close();
    }
    let allLeads = [];
    try {
        const existingRaw = await readFile(outPath, 'utf-8');
        const existingParsed = LeadsFileSchema.parse(JSON.parse(existingRaw));
        allLeads = existingParsed.leads;
    }
    catch {
        allLeads = [];
    }
    const leadMap = new Map();
    for (const l of allLeads) {
        leadMap.set(l.placeId, l);
    }
    for (const newLead of leads) {
        leadMap.set(newLead.placeId, newLead);
    }
    const finalLeads = Array.from(leadMap.values());
    const output = LeadsFileSchema.parse({
        schemaVersion: 1,
        generatedAt: new Date().toISOString(),
        query: { city: options.city, sector: options.sector },
        leads: finalLeads,
    });
    // Backup previo antes de sobreescribir leads.json
    try {
        await copyFile(outPath, `${outPath}.bak`);
    }
    catch {
        // No existe archivo previo: no hay nada que respaldar
    }
    await writeFile(outPath, JSON.stringify(output, null, 2), 'utf-8');
    const stats = {
        total: leads.length,
        segmentA: leads.filter((l) => l.segment === 'A').length,
        segmentB: leads.filter((l) => l.segment === 'B').length,
        withEmail: leads.filter((l) => l.email).length,
        auditDone: leads.filter((l) => l.auditStatus === 'done').length,
        auditTemplate: leads.filter((l) => l.auditStatus === 'template').length,
        auditPending: leads.filter((l) => l.auditStatus === 'pending').length,
    };
    console.log(`\nDone -> ${outPath}`);
    console.log(JSON.stringify(stats, null, 2));
}

function getTag(html, regex) {
    const m = html.match(regex);
    return m ? m[1].trim() : null;
}
export function analyzeSeo(input) {
    const { html } = input;
    const fails = [];
    // title
    const title = getTag(html, /<title[^>]*>([^<]*)<\/title>/i);
    if (title === null)
        fails.push('missing title tag');
    else if (title.length < 30)
        fails.push('title too short (<30)');
    else if (title.length > 60)
        fails.push('title too long (>60)');
    // meta description
    const metaDesc = getTag(html, /<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["']/i) ?? getTag(html, /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["']/i);
    if (metaDesc === null)
        fails.push('missing meta description');
    else if (metaDesc.length < 70)
        fails.push('meta description too short (<70)');
    else if (metaDesc.length > 160)
        fails.push('meta description too long (>160)');
    // H1
    const h1Count = (html.match(/<h1[\s>]/gi) ?? []).length;
    if (h1Count === 0)
        fails.push('missing H1');
    else if (h1Count > 1)
        fails.push('multiple H1 tags');
    // alts
    const imgs = html.matchAll(/<img\b[^>]*>/gi);
    let total = 0;
    let noAlt = 0;
    for (const img of imgs) {
        total++;
        const alt = img[0].match(/alt=["']([^"']*)["']/i);
        if (!alt || alt[1].trim() === '')
            noAlt++;
    }
    if (total > 0 && noAlt / total > input.imgNoAltRatio) {
        fails.push(`${noAlt}/${total} images without alt text`);
    }
    // schema.org LocalBusiness
    if (!/application\/ld\+json/i.test(html) || !/LocalBusiness|Organization/i.test(html)) {
        fails.push('missing LocalBusiness structured data');
    }
    if (!input.hasRobotsTxt)
        fails.push('missing robots.txt');
    if (!input.hasSitemapXml)
        fails.push('missing sitemap.xml');
    if (!/<link[^>]+rel=["']canonical["']/i.test(html))
        fails.push('missing canonical');
    if (!/property=["']og:title["']/i.test(html))
        fails.push('missing Open Graph');
    if (!/<link[^>]+rel=["'][^"']*icon["']/i.test(html))
        fails.push('missing favicon');
    if (input.textWordCount < input.thinContentWords) {
        fails.push(`thin content (${input.textWordCount} words)`);
    }
    // mixed content
    if (input.isHttps && /(src|href)=["']http:\/\//i.test(html)) {
        fails.push('mixed HTTP content on HTTPS');
    }
    return fails;
}

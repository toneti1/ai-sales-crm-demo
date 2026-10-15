// Segment A (no owned website) and down sites: template audit, zero LLM cost.
export function buildTemplateAudit(input) {
    if (input.siteDown) {
        return {
            painPoints: [
                {
                    fact: 'siteDown=true',
                    issue: 'The business website does not load: customers who look for it leave for competitors',
                    impact: 'high',
                },
            ],
            opportunities: [
                {
                    automation: 'Website rebuild + managed hosting',
                    solvesFact: 'siteDown=true',
                    pitchLine: 'your current website is not working and is losing customers every day',
                },
            ],
            seoFails: ['website down'],
            suggestedAngle: 'Their website is not working: offer an urgent fix or a new website.',
            summary: `${input.name} has a down or inaccessible website. Every failed search is a lost customer. Direct web development opportunity with urgency as the hook.`,
        };
    }
    const socialPain = input.socialOnly
        ? 'Their only online presence is a social network: they do not control the channel, do not rank properly on Google, and cannot capture customer data'
        : 'No website, or not attached on Google Maps: invisible on Google web search for customers seeking their services';
    return {
        painPoints: [
            {
                fact: 'no website (or not attached on Google Maps)',
                issue: socialPain,
                impact: 'high',
            },
            {
                fact: 'missing LocalBusiness structured data',
                issue: 'Without a website attached, local web SEO is not possible: they appear on Maps, but not properly in Google web search',
                impact: 'medium',
            },
        ],
        opportunities: [
            {
                automation: 'Business website with local SEO',
                solvesFact: 'no website (or not attached on Google Maps)',
                pitchLine: `be visible when someone searches for ${input.sector} in ${input.city}`,
            },
            {
                automation: 'Online booking or contact flow (form + WhatsApp Business)',
                solvesFact: 'no website (or not attached on Google Maps)',
                pitchLine: 'turn visits into customers even outside business hours',
            },
        ],
        seoFails: ['no website (or not attached on Google Maps)'],
        suggestedAngle: `No website or not attached on Google Maps: sell Google visibility for ${input.sector} searches in ${input.city}.`,
        summary: `${input.name} (${input.sector}, ${input.city}) has no website or it is not attached on Google Maps. Clear opportunity: website with local SEO and online lead/booking capture.`,
    };
}

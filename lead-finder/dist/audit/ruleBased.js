export function buildRuleBasedAudit(input) {
    const painPoints = [];
    const opportunities = [];
    const facts = input.facts;
    // 1. Site Speed
    if (facts.loadTimeMs > 3000) {
        const secs = (facts.loadTimeMs / 1000).toFixed(1);
        painPoints.push({
            fact: `loadTimeMs=${facts.loadTimeMs}`,
            issue: `Page takes over ${secs}s to load, causing potential clients to leave before seeing your services.`,
            impact: facts.loadTimeMs > 5000 ? 'high' : 'medium',
        });
        opportunities.push({
            automation: 'Website speed & image optimization',
            solvesFact: `loadTimeMs=${facts.loadTimeMs}`,
            pitchLine: `We can optimize website assets to drop load time under 2 seconds and retain more visitors.`,
        });
    }
    // 2. HTTPS Security
    if (!facts.https) {
        painPoints.push({
            fact: 'https=false',
            issue: 'The website is unencrypted (HTTP), triggering security warnings in modern web browsers.',
            impact: 'high',
        });
        opportunities.push({
            automation: 'SSL security configuration',
            solvesFact: 'https=false',
            pitchLine: 'Encrypt your website with HTTPS to remove browser warnings and build instant visitor trust.',
        });
    }
    // 3. Contact Form & Booking
    if (!facts.hasContactForm && !facts.bookingEngine) {
        painPoints.push({
            fact: 'hasContactForm=false',
            issue: 'Missing an online booking or contact form for visitors who prefer submitting inquiries digitally.',
            impact: 'high',
        });
        opportunities.push({
            automation: 'Online booking and quote capture form',
            solvesFact: 'hasContactForm=false',
            pitchLine: 'Add an automated request form above the fold to convert website traffic into qualified leads 24/7.',
        });
    }
    // 4. Chatbot / AI Assistant
    if (!facts.chatWidget && !facts.hasChatbot) {
        painPoints.push({
            fact: 'chatWidget=false',
            issue: 'No automated chat widget to answer client questions or capture leads outside of business hours.',
            impact: 'medium',
        });
        if (opportunities.length < 3) {
            opportunities.push({
                automation: '24/7 AI chat assistant',
                solvesFact: 'chatWidget=false',
                pitchLine: 'Deploy an automated assistant on your site to answer FAQs and capture inquiries day or night.',
            });
        }
    }
    // 5. Mobile Responsiveness
    if (facts.mobileOverflow) {
        painPoints.push({
            fact: 'mobileOverflow=true',
            issue: 'Layout overflows on small screens, causing horizontal scrolling and poor mobile navigation.',
            impact: 'high',
        });
        if (opportunities.length < 3) {
            opportunities.push({
                automation: 'Mobile-first responsive optimization',
                solvesFact: 'mobileOverflow=true',
                pitchLine: 'Fix mobile layout alignment so smartphone visitors can browse and contact effortlessly.',
            });
        }
    }
    // 6. Email Retention
    if (!facts.newsletter) {
        painPoints.push({
            fact: 'newsletter=false',
            issue: 'No automated email newsletter or lead capture for long-term customer retention.',
            impact: 'low',
        });
    }
    // Fallback pain point if clean site
    if (painPoints.length === 0) {
        painPoints.push({
            fact: 'conversion optimization',
            issue: 'The website is functional but lacks clear trust signals and automated client follow-ups.',
            impact: 'low',
        });
        opportunities.push({
            automation: 'Automated CRM follow-up integration',
            solvesFact: 'conversion optimization',
            pitchLine: 'Connect your website forms directly to automated email follow-ups to close leads faster.',
        });
    }
    const trimmedPainPoints = painPoints.slice(0, 5);
    const trimmedOpportunities = opportunities.slice(0, 3);
    const mainIssue = trimmedPainPoints[0].issue;
    return {
        painPoints: trimmedPainPoints,
        opportunities: trimmedOpportunities,
        seoFails: input.seoFails,
        suggestedAngle: `Address ${input.name}'s key bottleneck: ${mainIssue}`,
        summary: `${input.name} in ${input.city} (${input.sector}) has ${trimmedPainPoints.length} technical opportunity area(s). Main bottleneck: ${mainIssue}. Recommending ${trimmedOpportunities[0]?.automation || 'website modernization'}.`,
    };
}

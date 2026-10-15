export function computePriority(input) {
    let score = 0;
    const reasons = [];
    if (input.email) {
        score += 3;
        reasons.push('public email found (+3)');
    }
    if (input.segment === 'A') {
        score += 2;
        reasons.push('no owned website (+2)');
    }
    if (input.seoFailsCount >= 3) {
        score += 2;
        reasons.push(`poor SEO: ${input.seoFailsCount} failures (+2)`);
    }
    if (input.rating !== null && input.rating >= 4.5) {
        score += 1;
        reasons.push(`rating ${input.rating} >=4.5 (+1)`);
    }
    if (input.reviewCount > 100) {
        score += 1;
        reasons.push(`${input.reviewCount} reviews: established business (+1)`);
    }
    if (!input.phone) {
        score -= 1;
        reasons.push('missing phone (-1)');
    }
    const priority = score >= 5 ? 'high' : score >= 3 ? 'medium' : 'low';
    return { priority, reasons };
}

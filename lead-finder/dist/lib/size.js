// Size proxy: Maps does not expose employee count. Buckets use review count.
export function sizeFromReviews(reviewCount) {
    if (reviewCount < 15)
        return 'micro';
    if (reviewCount <= 100)
        return 'small';
    return 'medium';
}
